"""Tiny stdlib-only HTTP viewer for tools/geo/route_geometry.py output.

Serves a Leaflet page (viewer/index.html) plus three JSON endpoints backed
directly by the fixture files -- no build step, no third-party dependency.

Usage (run from the repo root):
  uv run --project tools/geo python -m tools.geo.viewer
  uv run --project tools/geo python -m tools.geo.viewer --port 8010
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

_ROUTE_ID_RE = re.compile(r"[A-Za-z0-9_-]+")

REPO_ROOT = Path(__file__).resolve().parents[3]
VIEWER_DIR = Path(__file__).resolve().parent
LOCATIONS_PATH = REPO_ROOT / "systems/masterdata/fixtures/locations.jsonl"
ROUTES_PATH = REPO_ROOT / "systems/tms/fixtures/routes.yaml"
GEOMETRY_DIR = REPO_ROOT / "systems/tms/fixtures/route-geometry"
KEEPOUT_ZONES_PATH = REPO_ROOT / "tools/geo/keepout_zones.yaml"


def load_locations() -> list[dict]:
    out = []
    for line in LOCATIONS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def load_routes() -> list[dict]:
    routes = yaml.safe_load(ROUTES_PATH.read_text(encoding="utf-8"))["routes"]
    return [
        {"id": r["id"], "lane": r["lane_id"], "contracted": "contracted" in r.get("roles", [])}
        for r in routes
    ]


def load_keepout_zones() -> list[dict]:
    return (
        yaml.safe_load(KEEPOUT_ZONES_PATH.read_text(encoding="utf-8")).get("zones")
        or []
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter default logging
        print(f"{self.address_string()} - {fmt % args}")

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str, status=200):
        body = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_file(VIEWER_DIR / "index.html", "text/html; charset=utf-8")
        elif self.path == "/api/locations":
            self._send_json(load_locations())
        elif self.path == "/api/routes":
            self._send_json(load_routes())
        elif self.path == "/api/keepout-zones":
            self._send_json(load_keepout_zones())
        elif self.path.startswith("/api/geometry/") and self.path.endswith(".geojson"):
            route_id = self.path.removeprefix("/api/geometry/").removesuffix(".geojson")
            if not _ROUTE_ID_RE.fullmatch(route_id):
                self._send_json({"error": f"invalid route id {route_id!r}"}, status=400)
                return
            geo_path = GEOMETRY_DIR / f"{route_id}.geojson"
            if geo_path.is_file():
                self._send_file(geo_path, "application/geo+json")
            else:
                self._send_json(
                    {"error": f"no geometry for route {route_id!r}"}, status=404
                )
        else:
            self._send_json({"error": "not found"}, status=404)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not GEOMETRY_DIR.is_dir():
        raise SystemExit(
            f"{GEOMETRY_DIR} missing -- run `uv run tools/geo/route_geometry.py` first"
        )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
