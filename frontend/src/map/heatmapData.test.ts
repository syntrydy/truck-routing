import { describe, expect, it } from "vitest";

import { sampleHeatmap } from "../test/plan.ts";
import { buildHeatmapFrames, cellSizeDeg } from "./heatmapData.ts";

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

  it("scales risk as the level over four, so a colour is a level of the legend", () => {
    const frames = buildHeatmapFrames(heatmap, "risk");

    expect(
      frames[2]?.features.map(({ properties }) => [properties.value, properties.known]),
    ).toEqual([
      [0, true],
      [0.5, true],
      [0.5, true],
    ]);
    expect(frames[4]?.features[1]?.properties.value).toBe(1);
  });

  it("gives every point the grid spacing, to size its circle", () => {
    const [first] = buildHeatmapFrames(heatmap, "risk");

    for (const feature of first?.features ?? []) {
      expect(feature.properties.cell).toBeCloseTo(0.8, 5); // the rows of the sample are 1.4 and 0.8 apart
    }
  });

  it("marks unknown points, which are drawn grey and never blended", () => {
    const [first] = buildHeatmapFrames(heatmap, "risk");

    expect(first?.features[2]?.properties).toMatchObject({ value: 0, known: false });
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

describe("cellSizeDeg", () => {
  it("is the smallest step between rows of latitude, however the points are ordered", () => {
    const points = [
      [40.4, -100],
      [40.0, -100.2],
      [40.2, -100],
      [40.0, -100],
      [40.8, -99.8],
    ];

    expect(cellSizeDeg(points)).toBeCloseTo(0.2);
  });

  it("does not take a gap in the lattice, where the mask cut it, for the spacing", () => {
    expect(
      cellSizeDeg([
        [40.0, -100],
        [40.4, -100],
        [41.2, -100],
      ]),
    ).toBeCloseTo(0.4);
  });

  it.each([
    [[]],
    [[[40.0, -100]]],
    [
      [
        [40.0, -100],
        [40.0, -99.8],
      ],
    ],
  ])("is the weather cache's 0.1 when there is only one row (%j)", (points) => {
    expect(cellSizeDeg(points)).toBe(0.1);
  });
});
