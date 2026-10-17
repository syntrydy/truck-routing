# Recorded OSRM responses

Real responses from the public OSRM demo server (`router.project-osrm.org`, car profile),
recorded on 2026-10-17 with the query the adapter sends
(`overview=full&geometries=geojson&annotations=distance,duration&steps=false`).

| File | Trip | Notes |
| --- | --- | --- |
| `two_routes.json` | Boulder, CO to Fort Collins, CO, `alternatives=3` | the server returned two routes |
| `one_route.json` | Denver, CO to Colorado Springs, CO, `alternatives=3` | the server returned a single route |
| `via_waypoint.json` | Denver to Boulder via a point north-west of Denver, `alternatives=false` | one route with two legs |
| `no_route.json` | Denver to Honolulu | HTTP 400 with `code: NoRoute` |

The public server rarely returns three alternatives (a dozen city pairs gave one or two), so
the three-route case is built in the tests from `two_routes.json`.

The files are reduced: each route keeps about 40 points per leg, and every skipped stretch is
merged into the next kept segment (its `distance` and `duration` annotations are summed), so
route and leg totals are unchanged and the geometry and annotations stay aligned. The
waypoint `hint` strings and `data_version` were removed.

Map data © OpenStreetMap contributors (ODbL). Routing by OSRM.
