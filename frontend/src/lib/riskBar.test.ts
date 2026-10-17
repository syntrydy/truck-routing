import { describe, expect, it } from "vitest";

import { route } from "../test/plan.ts";
import { formatMiles } from "./format.ts";
import { barSegments, segmentLabel } from "./riskBar.ts";

const summary = (milesByLevel: Record<string, number>, unknownMiles = 0) => ({
  ...route("x", 1, [], []).summary,
  miles_by_level: milesByLevel,
  unknown_miles: unknownMiles,
});

describe("barSegments", () => {
  it("lists the levels from low to no travel, then unknown", () => {
    const segments = barSegments(
      summary({ NO_TRAVEL: 5, LOW: 50, SEVERE: 5, HIGH: 20, MODERATE: 10 }, 10),
    );

    expect(segments.map((segment) => segment.level)).toEqual([
      "LOW",
      "MODERATE",
      "HIGH",
      "SEVERE",
      "NO_TRAVEL",
      "UNKNOWN",
    ]);
  });

  it("gives each its share of the route", () => {
    const segments = barSegments(summary({ LOW: 75, HIGH: 25 }));

    expect(segments).toEqual([
      { level: "LOW", miles: 75, percent: 75 },
      { level: "HIGH", miles: 25, percent: 25 },
    ]);
  });

  it("counts the unknown miles in the whole", () => {
    const segments = barSegments(summary({ LOW: 60 }, 40));

    expect(segments.map((segment) => segment.percent)).toEqual([60, 40]);
  });

  it("leaves out levels with no miles", () => {
    const segments = barSegments(summary({ LOW: 10, MODERATE: 0, HIGH: 0 }));

    expect(segments.map((segment) => segment.level)).toEqual(["LOW"]);
  });

  it("adds up to 100 percent", () => {
    const segments = barSegments(summary({ LOW: 33.3, MODERATE: 41.1, HIGH: 7.7 }, 3.3));

    expect(segments.reduce((sum, segment) => sum + segment.percent, 0)).toBeCloseTo(100);
  });

  it("is empty for a route with no miles at all", () => {
    expect(barSegments(summary({}))).toEqual([]);
    expect(barSegments(summary({ LOW: 0 }, 0))).toEqual([]);
  });
});

describe("segmentLabel", () => {
  it("is the level in words and the miles", () => {
    expect(segmentLabel({ level: "MODERATE", miles: 120, percent: 12 }, formatMiles)).toBe(
      "Moderate 120 mi",
    );
    expect(segmentLabel({ level: "NO_TRAVEL", miles: 4.5, percent: 1 }, formatMiles)).toBe(
      "No travel 4.5 mi",
    );
    expect(segmentLabel({ level: "UNKNOWN", miles: 30, percent: 3 }, formatMiles)).toBe(
      "Unknown 30 mi",
    );
  });
});
