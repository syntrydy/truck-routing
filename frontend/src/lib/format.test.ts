import { describe, expect, it } from "vitest";

import { formatDuration, formatMiles } from "./format.ts";

describe("formatDuration", () => {
  it.each([
    [0, "0 min"],
    [29, "0 min"],
    [31, "1 min"],
    [45 * 60, "45 min"],
    [59 * 60 + 40, "1 h"],
    [3600, "1 h"],
    [2 * 3600, "2 h"],
    [3600 + 5 * 60, "1 h 5 min"],
    [17 * 3600 + 5 * 60, "17 h 5 min"],
    [100 * 3600, "100 h"],
    [-20, "0 min"],
  ])("writes %d s as %s", (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text);
  });
});

describe("formatMiles", () => {
  it.each([
    [0, "0 mi"],
    [42.5, "42.5 mi"],
    [42.04, "42 mi"],
    [99.9, "99.9 mi"],
    [100, "100 mi"],
    [1003.1, "1,003 mi"],
    [1067.6, "1,068 mi"],
  ])("writes %d as %s", (miles, text) => {
    expect(formatMiles(miles)).toBe(text);
  });
});
