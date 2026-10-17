import type { PlanResponse, RiskLevel } from "../api/types.ts";
import { LEVEL_STYLES } from "./risk.ts";

type Summary = PlanResponse["routes"][number]["summary"];

export interface BarSegment {
  level: RiskLevel;
  miles: number;
  /** Share of the route, 0 to 100. */
  percent: number;
}

/** Known levels from low to no travel, then unknown, as the bar and its legend list them. */
const ORDER: readonly RiskLevel[] = ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL", "UNKNOWN"];

/** The stretches of a route by risk level, in order, leaving out levels with no miles. */
export function barSegments(summary: Summary): BarSegment[] {
  const miles = (level: RiskLevel): number =>
    level === "UNKNOWN" ? summary.unknown_miles : (summary.miles_by_level[level] ?? 0);
  const total = ORDER.reduce((sum, level) => sum + miles(level), 0);
  if (total <= 0) {
    return [];
  }
  return ORDER.filter((level) => miles(level) > 0).map((level) => ({
    level,
    miles: miles(level),
    percent: (miles(level) / total) * 100,
  }));
}

/** The text for a segment, e.g. `Moderate 120 mi`. */
export function segmentLabel(segment: BarSegment, formatMiles: (miles: number) => string): string {
  return `${LEVEL_STYLES[segment.level].label} ${formatMiles(segment.miles)}`;
}
