# Recorded Open-Meteo responses

Real, unreduced responses from the public Open-Meteo forecast API, recorded on 2026-10-17 with
the query the adapter sends (`hourly=wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,
weather_code`, `wind_speed_unit=mph`, `precipitation_unit=inch`, `timeformat=unixtime`,
`timezone=GMT`, `start_date=2026-10-18`, `end_date=2026-10-20`).

| File | Request | Notes |
| --- | --- | --- |
| `four_points.json` | Seattle, Mount Rainier, Loveland Pass, Minneapolis (rounded to 0.1°) | a JSON array with one object per place, in request order; Loveland Pass has real drizzle (weather code 51) |
| `single_point.json` | Denver area | one place comes back as a single object, not an array |
| `bad_request.json` | latitude 999 | HTTP 400 with `{"error": true, "reason": ...}` |

Things the recordings show that the adapter relies on:

- The wind unit is reported as `mp/h` (not `mph`); precipitation as `inch`.
- The reported `latitude` / `longitude` are the weather model's grid cell (39.69 for a request
  at 39.7), so results are matched to requests by position, never by returned coordinates.
- `hourly.time` is unix seconds, one entry per hour, here 72 entries for three UTC days.

Weather data by Open-Meteo.com, licensed CC BY 4.0.
