import { describe, expect, it } from "vitest";

import { BAND_STARTS, bandPosition, pointPosition, type HeatmapFrame } from "./heatmap.ts";

describe("bandPosition", () => {
  const wind = BAND_STARTS.wind;

  it.each([
    [-5, 0],
    [0, 0],
    [12.5, 0.125],
    [25, 0.25], // the start of Moderate is a quarter of the way
    [30, 0.375],
    [35, 0.5],
    [40, 0.625],
    [45, 0.75],
    [50, 0.875],
    [55, 1], // the start of No travel is the end
    [90, 1],
  ])("puts wind of %d mph at %d on the scale", (value, position) => {
    expect(bandPosition(value, wind)).toBeCloseTo(position);
  });

  it("uses the bands of each variable", () => {
    expect(bandPosition(0.1, BAND_STARTS.rain)).toBeCloseTo(0.25);
    expect(bandPosition(0.5, BAND_STARTS.rain)).toBeCloseTo(0.75);
    expect(bandPosition(1, BAND_STARTS.rain)).toBe(1);
    expect(bandPosition(0.5, BAND_STARTS.snow)).toBeCloseTo(0.25);
    expect(bandPosition(2, BAND_STARTS.snow)).toBeCloseTo(0.75);
    expect(bandPosition(3, BAND_STARTS.snow)).toBe(1);
  });

  it("never goes backwards as the reading rises", () => {
    let previous = -1;
    for (let value = 0; value <= 70; value += 0.5) {
      const position = bandPosition(value, wind);
      expect(position).toBeGreaterThanOrEqual(previous);
      previous = position;
    }
  });
});

describe("pointPosition", () => {
  const frame: HeatmapFrame = {
    risk: [0, 2, 4, -1],
    wind: [10, 35, null, 60],
    rain: [0, 0.25, null, 2],
    snow: [0, 1, null, 5],
  };

  it("reads risk as the level over four", () => {
    expect([0, 1, 2, 3].map((index) => pointPosition("risk", frame, index))).toEqual([
      0,
      0.5,
      1,
      null,
    ]);
  });

  it.each(["wind", "rain", "snow"] as const)(
    "reads %s on the scale, null when unknown",
    (variable) => {
      const positions = [0, 1, 2, 3].map((index) => pointPosition(variable, frame, index));

      expect(positions[0]).toBeCloseTo(variable === "wind" ? 10 / 25 / 4 : 0);
      expect(positions[1]).toBeCloseTo(0.5);
      expect(positions[2]).toBeNull();
      expect(positions[3]).toBe(1);
    },
  );

  it("is null for a point the frame does not have", () => {
    expect(pointPosition("risk", frame, 9)).toBeNull();
    expect(pointPosition("wind", frame, 9)).toBeNull();
  });
});
