# 4. The heatmap travels in the plan response

Status: accepted

## Context

The forecast slider must feel instant: dragging it should redraw the map within a frame. The map shows 49 hours (0 to 48) of weather for the corridor along the routes. Fetching a frame per slider step would put the network, and the weather provider's rate limits, in the path of every drag.

## Decision

`POST /api/plan` returns the whole heatmap with the routes: a masked grid of at most 200 points along the corridor, and 49 frames with the risk level, wind, rain and snow for each point. The grid uses the same weather cache as the checkpoints. The browser builds the 49 frames of map data once per plan and per variable, and the slider only changes which frame the map draws, at most once per animation frame.

## Consequences

- Moving the slider never touches the network, and works offline once a plan is in.
- The response is larger (about 175 KB raw, 19 KB gzipped for a 50-mile trip), well inside the 300 KB gzipped budget. The grid cap keeps long trips from growing without bound.
- One plan fetches weather for the grid and the checkpoints together, so the cost of a plan is bounded by the grid cap rather than by how far the user drags.
- Showing a different variable (wind, rain, snow) needs no new request.
