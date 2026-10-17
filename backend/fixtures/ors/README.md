# openrouteservice fixtures (constructed, not recorded)

These files are **not recorded from the real service**: openrouteservice needs an API key and
none was available. They follow the structure described in the openrouteservice documentation
(a GeoJSON `FeatureCollection` with `properties.segments[].steps[]`, `way_points` and
`summary`, and an `error` object with a numeric `code`), and they reuse the **real road
geometry and per-segment numbers of the recorded OSRM responses** in `../osrm/`, regrouped
into steps, so the data is realistic.

What is documented: the endpoint, the GeoJSON structure, and error codes 2009 (route could not
be found between locations) and 2010 (point was not found). What is assumed from public ORS
examples and has not been confirmed here: the exact step fields, the shape of error bodies,
the `Authorization` header and the request body. The adapter reads strictly, so a wrong
assumption shows up as an `UpstreamContractError` rather than a wrong route, and the opt-in
live test (`ORS_API_KEY=... pytest -m live`) checks the adapter against the real service.

| File | Content |
| --- | --- |
| `one_route.json` | one route in three steps plus the arrival step |
| `via_waypoint.json` | one route through a waypoint: two segments, `way_points` of three indices |
| `route_not_found.json` | error 2009 |
| `point_not_found.json` | error 2010 |

Map data © OpenStreetMap contributors (ODbL).
