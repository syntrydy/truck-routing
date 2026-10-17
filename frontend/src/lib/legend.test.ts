import { describe, expect, it } from "vitest";

import { legendEntries } from "./legend.ts";

describe("legendEntries", () => {
  it("names the levels for risk, then unknown", () => {
    expect(legendEntries("risk", "").map((entry) => entry.text)).toEqual([
      "Low",
      "Moderate",
      "High",
      "Severe",
      "No travel",
      "Unknown: no forecast",
    ]);
  });

  it("gives the readings behind each colour for wind", () => {
    expect(legendEntries("wind", "mph").map((entry) => entry.text)).toEqual([
      "Low: under 25 mph",
      "Moderate: 25 to 35 mph",
      "High: 35 to 45 mph",
      "Severe: 45 to 55 mph",
      "No travel: 55 mph or more",
      "Unknown: no forecast",
    ]);
  });

  it("does the same for rain and snow", () => {
    expect(legendEntries("rain", "in/hr").map((entry) => entry.text)).toContain(
      "High: 0.25 to 0.5 in/hr",
    );
    expect(legendEntries("snow", "in/hr").map((entry) => entry.text)).toContain(
      "No travel: 3 in/hr or more",
    );
  });

  it("pairs every entry with a level, ending with the unknown grey", () => {
    const entries = legendEntries("wind", "mph");

    expect(entries.map((entry) => entry.level)).toEqual([
      "LOW",
      "MODERATE",
      "HIGH",
      "SEVERE",
      "NO_TRAVEL",
      "UNKNOWN",
    ]);
  });
});
