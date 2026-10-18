# 1. Routing provider: OSRM first, openrouteservice behind it

Status: accepted

## Context

The app needs up to three distinct driving routes between two US places, with geometry and per-segment distance and duration. Candidates are hosted services that are free to use. A truck-specific profile would be ideal, but the free options differ in what they offer:

- **OSRM public demo server**: no key, returns alternatives, car profile only, best effort, about one request per second.
- **openrouteservice**: a `driving-hgv` truck profile, needs a free key, but returns alternatives only up to about 100 km.
- Self-hosting OSRM or Valhalla is out of reach on a free web service.

## Decision

OSRM is the primary provider. openrouteservice is an optional fallback, active only when `ORS_API_KEY` is set. Both sit behind one `RoutingProvider` interface and a chain that tries them in order. When OSRM returns fewer than three routes, the planner builds detours itself by routing through a via point beside the midpoint, then drops duplicates and detours that are too long. OSRM calls are spaced at least 1.1 seconds apart.

## Consequences

- Routes are for a car, so truck restrictions (height, weight limits, truck bans) are not guaranteed. This is documented as a known limit, and the response carries a note.
- The app works with no key and no account. A key only adds resilience.
- The demo server can be slow or unavailable; the circuit breaker, one retry and the fallback keep a failure from becoming a hang, and the error says what failed.
- Replacing the provider (a paid OSRM, Valhalla) means one new adapter, with no change to the domain.
