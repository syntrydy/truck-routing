import { describe, expect, it } from "vitest";

import { route, samplePlan } from "../test/plan.ts";
import { checkpointFeatures, routeBounds, routeFeatures } from "./routeData.ts";

const NONE = { selectedId: null, hoveredId: null };

describe("routeFeatures", () => {
  const routes = samplePlan().routes;

  it("makes one line per route, with the route's own geometry", () => {
    const { features } = routeFeatures(routes, NONE);

    expect(features.map((feature) => feature.properties.id)).toEqual(["r1", "r2"]);
    expect(features[0]?.geometry).toEqual({
      type: "LineString",
      coordinates: routes[0]?.geometry.coordinates,
    });
    expect(features[0]?.properties).toMatchObject({
      label: "Route R1",
      rank: 1,
      recommended: true,
    });
    expect(features[1]?.properties).toMatchObject({ rank: 2, recommended: false });
  });

  it("gives each route its letter and the pattern of its line, whatever its rank", () => {
    const lettered = routes.map((candidate, index) => ({
      ...candidate,
      label: `Route ${index === 0 ? "C" : "A"}`,
    }));

    const { features } = routeFeatures(lettered, NONE);

    expect(features.map((f) => [f.properties.letter, f.properties.pattern])).toEqual([
      ["C", "dotted"],
      ["A", "solid"],
    ]);
  });

  it("draws better routes over worse ones", () => {
    const [first, second] = routeFeatures(routes, NONE).features;

    expect(first?.properties.order).toBeGreaterThan(second?.properties.order ?? 0);
  });

  it("marks the selected and the hovered routes, and draws them on top", () => {
    const { features } = routeFeatures(routes, { selectedId: "r2", hoveredId: "r1" });
    const [r1, r2] = features;

    expect(r1?.properties.emphasis).toBe("hovered");
    expect(r2?.properties.emphasis).toBe("selected");
    expect(r2?.properties.order).toBeGreaterThan(r1?.properties.order ?? 0);
    expect(r1?.properties.order).toBeGreaterThan(2);
  });

  it("lets the selection win when the same route is hovered", () => {
    const { features } = routeFeatures(routes, { selectedId: "r1", hoveredId: "r1" });

    expect(features[0]?.properties.emphasis).toBe("selected");
    expect(features[1]?.properties.emphasis).toBe("normal");
  });

  it("is empty for no routes", () => {
    expect(routeFeatures([], NONE)).toEqual({ type: "FeatureCollection", features: [] });
  });
});

describe("checkpointFeatures", () => {
  const routes = samplePlan().routes;

  it("puts every checkpoint of every route in one set, longitude first", () => {
    const { features } = checkpointFeatures(routes, "r1");

    expect(features).toHaveLength(5);
    const first = routes[0]?.checkpoints[1];
    expect(features[1]?.geometry.coordinates).toEqual([first?.lon, first?.lat]);
  });

  it("carries what the layer and the popup need to find the checkpoint again", () => {
    const { features } = checkpointFeatures(routes, "r1");

    expect(features[2]?.properties).toEqual({
      routeId: "r1",
      index: 2,
      level: "HIGH",
      severity: 2,
      selected: true,
    });
  });

  it("marks only the selected route's checkpoints", () => {
    const { features } = checkpointFeatures(routes, "r2");

    expect(features.map((feature) => feature.properties.selected)).toEqual([
      false,
      false,
      false,
      true,
      true,
    ]);
  });

  it.each([
    ["UNKNOWN", -1],
    ["LOW", 0],
    ["MODERATE", 1],
    ["HIGH", 2],
    ["SEVERE", 3],
    ["NO_TRAVEL", 4],
  ] as const)("gives %s the severity %d", (level, severity) => {
    const { features } = checkpointFeatures([route("x", 1, [level], [[0, 0]])], null);

    expect(features[0]?.properties.severity).toBe(severity);
  });

  it("marks nothing when no route is selected", () => {
    const { features } = checkpointFeatures(routes, null);

    expect(features.some((feature) => feature.properties.selected)).toBe(false);
  });
});

describe("routeBounds", () => {
  it("surrounds every route", () => {
    expect(routeBounds(samplePlan().routes)).toEqual([
      [-105, 38],
      [-87.6, 41.9],
    ]);
  });

  it("copes with a single point", () => {
    expect(routeBounds([route("x", 1, [], [[-100, 40]])])).toEqual([
      [-100, 40],
      [-100, 40],
    ]);
  });

  it("is null when there is nothing to surround", () => {
    expect(routeBounds([])).toBeNull();
    expect(routeBounds([route("x", 1, [], [])])).toBeNull();
  });
});
