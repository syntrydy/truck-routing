# Recorded geocoding responses

Real, unreduced responses recorded on 2026-10-17 from the public Photon
(`photon.komoot.io`) and Nominatim (`nominatim.openstreetmap.org`) instances, with an
identifying User-Agent and more than a second between requests.

| File | Request | Notes |
| --- | --- | --- |
| `photon_city.json` | `q=denver&limit=8&lang=en` | eight places named Denver: a city, villages, hamlets, a UK district |
| `photon_address.json` | `q=1600 pennsylvania ave washington` | house-level results with `housenumber`, `street`, `city` |
| `photon_empty.json` | `q=qzxwvbnmpl` | no match: a FeatureCollection with no features |
| `nominatim_city.json` | `q=denver&format=jsonv2&limit=8&addressdetails=1&accept-language=en` | four places named Denver; `lat` and `lon` are strings |
| `nominatim_empty.json` | `q=qzxwvbnmpl` | no match: `[]` |

What the recordings show that the adapters rely on:

- Photon returns GeoJSON with `[lon, lat]`; its `type` is a coarse kind (`city`, `district`,
  `house`, `street`, ...) and many address fields are simply absent.
- Nominatim's `display_name` is long (it includes the county and postcode), so labels are built
  from `name` and the `address` object instead.
- "No match" is a valid, empty answer in both.

Map data © OpenStreetMap contributors (ODbL).
