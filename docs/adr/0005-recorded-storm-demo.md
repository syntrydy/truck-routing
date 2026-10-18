# 5. The demo replays a recorded storm through the real plan service

Status: accepted

## Context

On a calm day every route is Low, so a reviewer cannot see the risk bands, the load rules or the ranking at work, and the live weather depends on free services whose daily limit the shared host can use up. A demo must show danger, honestly labeled, and must not depend on any live service.

## Decision

`GET /api/demo` plans a fixed trip, Denver to Salt Lake City, with the same `PlanService` as a live plan. Only its two providers change: routing returns three recorded roads (I-80 through Wyoming, I-70 through Grand Junction, US-40 through Craig) and weather replays the Open-Meteo historical forecast of the wind storm of 17 January 2024, at 24 places along the roads. The storm is moved in time so that its worst hours begin at the request, whatever the hour of day, and a place takes the weather of the nearest recorded place. The response says `demo` as its routing and weather source; the web app turns that into a banner saying it is a recording and not a live forecast. The recordings and the script that makes them are in `backend/fixtures/demo` and `backend/scripts`.

## Consequences

- The demo exercises the live code (checkpoints, risk bands, load rules, ranking, heatmap), so what a reviewer sees is how the app decides; only the inputs are recorded.
- It works with no network and no quota, and is the same on every run for a given load.
- The load and the checkpoint spacing can change, the trip and the storm cannot.
- A real storm was chosen over an invented one, so the forecast is a true one; its strength is from the forecast model, not a measurement.
