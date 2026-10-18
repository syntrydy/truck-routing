# Recorded demo corridor

The stormy demo (`GET /api/demo`) replays these two files. They are recorded once with
`scripts/record_demo.py` (`cd backend && PYTHONPATH=. uv run python scripts/record_demo.py`); the
network is not used at any other time.

| File | Content |
| --- | --- |
| `denver_salt_lake_routes.json` | Denver, CO to Salt Lake City, UT by three roads, from the public OSRM server (car profile): I-80 through Wyoming, I-70 through Grand Junction and US-40 through Craig. Each route keeps a point about every 2 miles, with its real distance and duration. |
| `denver_salt_lake_weather.json` | The Open-Meteo historical forecast (`historical-forecast-api.open-meteo.com`) for the 6 UTC days of 2024-01-15 to 2024-01-20, hourly, at 24 places spaced about 45 miles apart along the three routes. |

The forecast is from a real winter storm: on 2024-01-17 the wind on I-80 near Laramie and Elk
Mountain, Wyoming, reached about 50 mph sustained and 75 mph in gusts. When it is replayed the
storm is moved in time so that it starts at the hour of the request, and every place on a plan
takes the weather of the nearest recorded place.

Map data © OpenStreetMap contributors (ODbL). Routing by OSRM. Weather data by
[Open-Meteo.com](https://open-meteo.com), licensed CC BY 4.0.
