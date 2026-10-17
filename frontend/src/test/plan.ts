import type { PlanResponse, RiskLevel } from "../api/types.ts";

type Route = PlanResponse["routes"][number];
type Checkpoint = Route["checkpoints"][number];

export function checkpoint(index: number, changes: Partial<Checkpoint> = {}): Checkpoint {
  return {
    index,
    mile: index * 25,
    lat: 41.9 - index * 0.5,
    lon: -87.6 - index * 1.5,
    eta: "2026-10-18T19:00:00Z",
    wind_mph: 12.3,
    gust_mph: 20,
    rain_in_hr: 0,
    snow_in_hr: 0,
    level: "LOW",
    reasons: [],
    ...changes,
  };
}

export function route(
  id: string,
  rank: number,
  levels: RiskLevel[],
  coordinates: number[][],
): Route {
  return {
    id,
    label: `Route ${id.toUpperCase()}`,
    rank,
    distance_mi: 100 * rank,
    duration_s: 6000 * rank,
    geometry: { type: "LineString", coordinates },
    summary: {
      miles_by_level: {},
      unknown_miles: 0,
      avg_risk: 0,
      worst_level: "LOW",
      low_confidence: false,
    },
    checkpoints: levels.map((level, index) => checkpoint(index, { level })),
  };
}

/**
 * A heatmap of three points for `frameCount` hours. At hour h: point 0 is calm, point 1 gets
 * worse with the hour (risk level up to 4, wind 10 + h mph), point 2 is unknown at hour 0 only.
 */
export function sampleHeatmap(frameCount = 49): PlanResponse["heatmap"] {
  return {
    start: "2026-10-18T19:00:00Z",
    points: [
      [41.9, -87.6],
      [40.5, -95],
      [39.7, -105],
    ],
    frames: Array.from({ length: frameCount }, (_, hour) => ({
      risk: [0, Math.min(hour, 4), hour === 0 ? -1 : 2],
      wind: [10, 10 + hour, hour === 0 ? null : 30],
      rain: [0, 0.3, hour === 0 ? null : 0],
      snow: [0, 0, hour === 0 ? null : 0],
    })),
  };
}

/** Two routes from Chicago towards Denver: r1 recommended, r2 the slower one to its south. */
export function samplePlan(): PlanResponse {
  return {
    recommended_route_id: "r1",
    recommendation_reason: "Lowest weather risk",
    banner: null,
    routes: [
      route(
        "r1",
        1,
        ["LOW", "MODERATE", "HIGH"],
        [
          [-87.6, 41.9],
          [-95, 41.5],
          [-105, 39.7],
        ],
      ),
      route(
        "r2",
        2,
        ["LOW", "UNKNOWN"],
        [
          [-87.6, 41.9],
          [-93, 38],
          [-105, 39.7],
        ],
      ),
    ],
    heatmap: sampleHeatmap(),
    notes: [],
    meta: {
      routing_source: "osrm",
      weather_source: "open-meteo",
      weather_stale: false,
      generated_at: "2026-10-18T18:00:00Z",
      request_id: "req-1",
    },
  };
}
