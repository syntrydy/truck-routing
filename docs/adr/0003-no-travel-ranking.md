# 3. No Travel miles rank before Severe miles

Status: accepted

## Context

The brief orders the ranking criteria with Severe first, and does not say how No Travel compares. Read literally, a route with a short No Travel stretch and no Severe miles would beat a route with a few Severe miles and no No Travel. That would recommend a stretch the app itself calls unsafe over one that is only very risky.

## Decision

Routes are ranked by this key, lower first: No Travel miles, Severe miles, High miles, average risk, duration. Miles are rounded to a tenth and average risk to a hundredth so that float noise cannot decide. When every route has some No Travel miles there is no recommendation: the response has no recommended route and the banner `NO_SAFE_ROUTE`, and the routes are still listed in rank order. Unknown miles never count as Low. The recommendation reason names the first criterion that separates the first route from the second.

## Consequences

- A No Travel route can never outrank a Severe one.
- The app says when it has no safe route to offer, instead of picking the least bad one without saying so.
- A route with much unknown weather is flagged as low confidence rather than ranked as if it were safe.
