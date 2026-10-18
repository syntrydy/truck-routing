# Recorded National Weather Service responses

Real responses from `api.weather.gov`, recorded on 2026-10-18 with the requests the adapter makes
(`/points/{lat},{lon}` with the point rounded to 0.1 degree, then the `forecastGridData` URL it names).
Both are reduced to the fields the adapter reads.

| File | Request | Notes |
| --- | --- | --- |
| `points_boulder.json` | `/points/40.0,-105.3` | the grid cell (office BOU, 53,74) and the URL of its raw forecast |
| `gridpoints_boulder.json` | `/gridpoints/BOU/53,74` | wind and gusts in km/h, precipitation and snowfall in mm; intervals of 1 to 6 hours, written as `start/ISO-8601 duration` |
| `gridpoints_storm.json` | made by hand | the same shape with a storm in it (45 mph wind, 60 mph gusts, 0.6 in of precipitation and 3 in of snow over 6 hours) so the conversions can be checked against known numbers |

Things the recordings show that the adapter relies on:

- Precipitation and snowfall are totals over the whole interval (`PT6H`), not per hour.
- Wind is reported per interval and `null` is possible for a value.
- The series start at 00:00 UTC of the day recorded, so earlier hours of the day are covered too, and run about 8 days ahead.
