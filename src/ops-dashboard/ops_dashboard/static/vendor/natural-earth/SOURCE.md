# Natural Earth 110m Admin-0 Countries

Source: https://github.com/nvkelso/natural-earth-vector (public domain,
[naturalearthdata.com](https://www.naturalearthdata.com/) — "no permission is
needed to use Natural Earth"). Vendored (not fetched at runtime) so the map
view (`/map`) works fully offline, consistent with this project's other
vendored reference data.

Trimmed from the original ~839KB to ~252KB: geometry + country name only,
every other Natural Earth attribute column dropped (scale rank, admin codes,
population estimates, etc. — none used by `/map`).
