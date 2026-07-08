# GeoNames attribution

The bundled offline city gazetteer (`engine/mappings/geo/cities.json`) is derived
from the [GeoNames](https://www.geonames.org) geographical database (the
`cities15000`, `admin1CodesASCII`, and `countryInfo` datasets), which is licensed
under the [Creative Commons Attribution 4.0 License](https://creativecommons.org/licenses/by/4.0/).

- Source: GeoNames — https://download.geonames.org/export/dump/
- License: CC BY 4.0
- Modifications: filtered to cities with population ≥ 15,000; reduced to
  `[name, country, admin1, lat, lng, population]`; coordinates rounded to
  4 decimal places. Regenerate with `packaging/build_gazetteer.py`.

This data is used **entirely offline** by `engine/scripts/geocode.py` at vault
build time — no GeoNames web services are called.
