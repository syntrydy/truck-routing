# 2. Risk band boundaries and load rules

Status: accepted

## Context

The brief gives risk bands for wind, rain and snow, and rules that raise the risk for heavy loads. It writes some edges as ranges and some as "greater than". Two readings of an edge value (is exactly 25 mph Low or Moderate?) change the result, so the choice must be made once and tested.

## Decision

- Bands are half-open: the lower bound belongs to the band. Wind of exactly 25 mph is Moderate.
- Where the brief says "greater than" for No Travel, the top edge of Severe is inclusive: rain of exactly 1.00 in/hr and snow of exactly 3.0 in/hr are Severe; anything above is No Travel.
- Load thresholds are strict: more than 30,000 lb, more than 40,000 lb.
- The load rules apply after the weather table, in order of severity, and a checkpoint takes the worst of its factors.
- Wind is classified on the sustained 10 m wind by default, as the brief's table reads. Gusts are always returned and shown; `RISK_WIND_BASIS=gust` switches the classification.
- The rain rate is rain plus showers.
- The bands live in tables as data, and the tests check both sides of every edge.

## Consequences

- Every edge value has one documented answer, and property tests keep the bands ordered.
- Gust-driven danger does not raise the level by default; the gust is still on screen, and a deployment that prefers caution can change the setting.
- If the brief's author meant a different edge, the change is one table entry and its tests.
