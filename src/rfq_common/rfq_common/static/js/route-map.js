// Shared Leaflet rendering logic for /map (all routes) and /routes/{id}
// (one route's mini-map) -- extracted here so both templates use the exact
// same antimeridian handling instead of maintaining two copies.

const RouteMapStatusColor = {
  available: "#16a34a", limited: "#d97706", degraded: "#d97706",
  unavailable: "#dc2626", unknown: "#6b7280",
};

// A vector GeoJSON layer renders exactly once -- unlike a raster tile layer,
// it does NOT repeat every 360deg of longitude, so dragging the map past its
// edge shows blank space instead of the expected continuously-wrapping
// landmasses. Render three shifted copies (-360/0/+360) so panning behaves
// like a normal web map. (This is a separate concern from how route LINES
// are drawn -- see splitAtAntimeridian below -- both are needed.)
function rmShiftLongitude(coords, delta) {
  if (typeof coords[0] === "number") return [coords[0] + delta, coords[1]];
  return coords.map((c) => rmShiftLongitude(c, delta));
}

function rmShiftGeoJSON(geojson, delta) {
  return {
    type: "FeatureCollection",
    features: geojson.features.map((f) => ({
      ...f,
      geometry: { type: f.geometry.type, coordinates: rmShiftLongitude(f.geometry.coordinates, delta) },
    })),
  };
}

function rmAddBasemap(map, geojsonUrl) {
  fetch(geojsonUrl || "/static/vendor/natural-earth/ne_110m_admin_0_countries.geojson")
    .then((r) => r.json())
    .then((geojson) => {
      const style = { color: "#94a3b8", weight: 1, fillColor: "#e2e8f0", fillOpacity: 0.5 };
      for (const delta of [-360, 0, 360]) {
        L.geoJSON(rmShiftGeoJSON(geojson, delta), { style }).addTo(map);
      }
    });
}

// A route crossing the antimeridian the short way (e.g. Shanghai lon ~121E
// -> LA lon ~-118W, short way is eastward across the Pacific) still can't be
// drawn as one straight segment in the DEFAULT (fitBounds-centered) view --
// it has to be split: exit at the +180 edge, re-enter at the -180 edge (or
// vice versa), same convention flight-path maps use. Returns an array of
// [[lat,lon],[lat,lon]] segments -- one if no crossing, two if there is one.
function splitAtAntimeridian(from, to) {
  const [lat1, lon1] = from;
  const [lat2, lon2] = to;

  let lon2u = lon2;
  if (lon2 - lon1 > 180) lon2u -= 360;
  else if (lon1 - lon2 > 180) lon2u += 360;

  if (lon2u === lon2) {
    return [[[lat1, lon1], [lat2, lon2]]]; // no crossing -- one segment, unchanged
  }

  const boundary = lon2u > lon1 ? 180 : -180; // which edge the line exits through
  const t = (boundary - lon1) / (lon2u - lon1);
  const latAtBoundary = lat1 + t * (lat2 - lat1);

  return [
    [[lat1, lon1], [latAtBoundary, boundary]],
    [[latAtBoundary, -boundary], [lat2, lon2]],
  ];
}

// routes: [{id, lane, status, points: [[lat,lon], ...], legs: [{from,to,mode}, ...]}, ...]
// opts.onLine(route, leafletLine): optional per-line callback (e.g. bindPopup)
// Returns legLayers: legLayers[routeIndex][legIndex] = [leafletLine, ...] --
// every straight-line layer drawn for that leg (1 or 2 antimeridian-split
// segments x 3 shifted basemap copies each), so a caller (M10:
// rmEnrichCurvedGeometry) can later remove EXACTLY those layers once a real
// curved replacement is ready, never guessing which layer belongs to which leg.
function rmDrawRoutes(map, routes, opts) {
  opts = opts || {};
  const allPoints = [];
  const legLayers = [];
  for (const r of routes) {
    const color = RouteMapStatusColor[r.status] || RouteMapStatusColor.unknown;
    const routeLegLayers = [];
    // r.points has every leg boundary (real waypoints), not just origin/dest --
    // draw one segment per consecutive pair so multi-leg routes actually bend
    // through their intermediate ports instead of looking like a direct route.
    for (let i = 0; i < r.points.length - 1; i++) {
      const layers = [];
      for (const segment of splitAtAntimeridian(r.points[i], r.points[i + 1])) {
        // Routes must appear in the shifted basemap copies too, or panning to
        // one shows landmasses with no route lines on them.
        for (const delta of [-360, 0, 360]) {
          const shifted = segment.map(([lat, lon]) => [lat, lon + delta]);
          const line = L.polyline(shifted, { color, weight: 3, opacity: 0.85 }).addTo(map);
          if (opts.onLine) opts.onLine(r, line);
          layers.push(line);
        }
      }
      routeLegLayers.push(layers);
    }
    legLayers.push(routeLegLayers);
    allPoints.push(...r.points);
  }
  if (allPoints.length) {
    map.fitBounds(L.latLngBounds(allPoints), { padding: opts.padding || [20, 20] });
    // Mercator distorts badly near the poles, and no route ever goes there --
    // rather than a hardcoded lat/lon box (which fights the container's own
    // aspect ratio and can force MORE area into view than intended), just
    // don't allow zooming/panning out past the view that actually fits the
    // real data.
    map.setMinZoom(map.getZoom());
    map.setMaxBounds(map.getBounds().pad(0.5));
  }
  return legLayers;
}

// M10: async, best-effort enrichment -- swaps each leg's straight-line
// fallback (already drawn by rmDrawRoutes, instantly) for geo-api's real
// curved geometry, fetched via ops-dashboard's own same-origin proxy
// (geometryUrl, default /map/legs/geometry). Fails OPEN per leg: a non-2xx
// response or a network error (geo-api down, slow, whatever) just leaves
// that leg's straight line in place -- a line is never removed unless its
// curved replacement is already drawn and ready.
function rmEnrichCurvedGeometry(map, routes, legLayers, opts) {
  opts = opts || {};
  const geometryUrl = opts.geometryUrl || "/map/legs/geometry";
  routes.forEach((r, routeIndex) => {
    const legs = r.legs || [];
    legs.forEach((leg, legIndex) => {
      const url = `${geometryUrl}?from=${encodeURIComponent(leg.from)}&to=${encodeURIComponent(leg.to)}&mode=${encodeURIComponent(leg.mode)}`;
      fetch(url)
        .then((resp) => (resp.ok ? resp.json() : null))
        .then((data) => {
          if (!data || !data.geometry) return;
          const color = RouteMapStatusColor[r.status] || RouteMapStatusColor.unknown;
          const feature = { type: "Feature", properties: {}, geometry: data.geometry };
          const collection = { type: "FeatureCollection", features: [feature] };
          const newLayers = [];
          for (const delta of [-360, 0, 360]) {
            const layer = L.geoJSON(rmShiftGeoJSON(collection, delta), {
              style: { color, weight: 3, opacity: 0.85 },
            }).addTo(map);
            if (opts.onLine) opts.onLine(r, layer);
            newLayers.push(layer);
          }
          const oldLayers = ((legLayers[routeIndex] || [])[legIndex]) || [];
          for (const oldLayer of oldLayers) map.removeLayer(oldLayer);
        })
        .catch(() => {}); // network error -- fails open, straight line stays
    });
  });
}

function rmInitMap(elementId, opts) {
  opts = opts || {};
  // mini: an inset thumbnail (route detail page) -- scroll-wheel zoom would
  // trap the page's own scroll the moment the cursor crosses the map, a bad
  // surprise on a small embedded map; the full-page /map view keeps it.
  const mapOpts = { worldCopyJump: true, scrollWheelZoom: !opts.mini };
  return L.map(elementId, mapOpts).setView([20, 30], 2);
}
