import { describe, expect, it } from "vitest";

import { routeLetter, routePattern } from "./routeStyle.ts";

describe("routeLetter", () => {
  it.each([
    ["Route A", "A"],
    ["Route C", "C"],
    ["route b ", "B"],
  ])("reads %s as %s", (label, letter) => {
    expect(routeLetter(label)).toBe(letter);
  });
});

describe("routePattern", () => {
  it("gives the first three routes three different patterns", () => {
    expect(["Route A", "Route B", "Route C"].map(routePattern)).toEqual([
      "solid",
      "dashed",
      "dotted",
    ]);
  });

  it("starts again after C, and never throws for an odd label", () => {
    expect(routePattern("Route D")).toBe("solid");
    expect(routePattern("")).toBeDefined();
    expect(routePattern("Route 1")).toBeDefined();
  });
});
