import { describe, expect, it } from "vitest";

import { sampleHeatmap } from "../test/plan.ts";
import { buildHeatmapFrames, HEAT_FLOOR } from "./heatmapData.ts";

describe("buildHeatmapFrames", () => {
  const heatmap = sampleHeatmap();

  it("makes one set of points for each hour", () => {
    const frames = buildHeatmapFrames(heatmap, "risk");

    expect(frames).toHaveLength(49);
    expect(frames.every((frame) => frame.features.length === 3)).toBe(true);
  });

  it("puts the points where the plan says, longitude first", () => {
    const [first] = buildHeatmapFrames(heatmap, "risk");

    expect(first?.features.map((feature) => feature.geometry.coordinates)).toEqual([
      [-87.6, 41.9],
      [-95, 40.5],
      [-105, 39.7],
    ]);
  });

  it("shares the geometry between hours and changes only the properties", () => {
    const frames = buildHeatmapFrames(heatmap, "risk");

    expect(frames[0]?.features[1]?.geometry).toBe(frames[30]?.features[1]?.geometry);
    expect(frames[0]?.features[1]?.properties).not.toEqual(frames[30]?.features[1]?.properties);
  });

  it("scales risk as the level over four, with a floor for the heat of calm places", () => {
    const frames = buildHeatmapFrames(heatmap, "risk");

    expect(frames[2]?.features.map((feature) => feature.properties)).toEqual([
      { value: 0, heat: HEAT_FLOOR, known: true }, // calm: faint, not nothing
      { value: 0.5, heat: 0.5, known: true },
      { value: 0.5, heat: 0.5, known: true },
    ]);
    expect(frames[4]?.features[1]?.properties).toEqual({ value: 1, heat: 1, known: true });
  });

  it("marks unknown points, which give no heat", () => {
    const [first] = buildHeatmapFrames(heatmap, "risk");

    expect(first?.features[2]?.properties).toEqual({ value: 0, heat: 0, known: false });
  });

  it.each(["wind", "rain", "snow"] as const)(
    "builds %s frames with unknown readings unknown",
    (variable) => {
      const [first, later] = buildHeatmapFrames(heatmap, variable);

      expect(first?.features[2]?.properties.known).toBe(false);
      expect(later?.features[2]?.properties.known).toBe(true);
    },
  );

  it("puts wind on the shared scale", () => {
    const frames = buildHeatmapFrames(heatmap, "wind");

    // Point 1 has wind of 10 + hour: 15 mph at hour 5, 25 mph (the start of Moderate) at hour 15.
    expect(frames[5]?.features[1]?.properties.value).toBeCloseTo(15 / 25 / 4);
    expect(frames[15]?.features[1]?.properties.value).toBeCloseTo(0.25);
  });

  it("makes no frames for a heatmap without any", () => {
    expect(buildHeatmapFrames({ ...heatmap, frames: [] }, "risk")).toEqual([]);
  });

  it("copes with a heatmap without points", () => {
    const frames = buildHeatmapFrames({ ...heatmap, points: [] }, "risk");

    expect(frames[0]?.features).toEqual([]);
  });
});
