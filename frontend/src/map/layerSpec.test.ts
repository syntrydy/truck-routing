import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";

import { LEVEL_STYLES } from "../lib/risk.ts";
import { FakeMap } from "./fakeMapLibre.ts";
import { installHeatmapLayers } from "./heatmapLayers.ts";
import { installRouteLayers } from "./routeLayers.ts";

/**
 * The fake map accepts anything, so these layers are also checked against MapLibre's own style
 * rules: a misplaced `zoom` or a wrong property name is a mistake the real map only reports in
 * the console, and then silently leaves the layer out.
 */
function styleWithOurLayers(): StyleSpecification {
  const map = new FakeMap({});
  installRouteLayers(map as unknown as MapLibreMap);
  installHeatmapLayers(map as unknown as MapLibreMap);
  return {
    version: 8,
    // The labels need the basemap's glyphs; the real style names them.
    glyphs: "https://tiles.example/fonts/{fontstack}/{range}.pbf",
    sources: Object.fromEntries(
      [...map.sources].map(([name, source]) => [name, { type: "geojson", data: source.spec.data }]),
    ),
    layers: map.layers as unknown as StyleSpecification["layers"],
  } as StyleSpecification;
}

describe("the layers we add", () => {
  it("are valid for MapLibre", () => {
    const problems = validateStyleMin(styleWithOurLayers()).map((problem) => problem.message);

    expect(problems).toEqual([]);
  });

  it("are all of them there to be checked", () => {
    expect(styleWithOurLayers().layers.map((layer) => layer.id)).toEqual([
      "routes-casing",
      "routes-line",
      "routes-line-dashed",
      "routes-line-dotted",
      "routes-label",
      "checkpoints",
      "heatmap-glow",
      "heatmap-points",
    ]);
  });

  it("draws each pattern in a layer of its own, because a pattern cannot vary by route", () => {
    const layers = styleWithOurLayers().layers;
    const filtered = (id: string) => layers.find((layer) => layer.id === id);

    expect(filtered("routes-line")).toMatchObject({ filter: ["==", ["get", "pattern"], "solid"] });
    expect(filtered("routes-line-dashed")).toMatchObject({
      filter: ["==", ["get", "pattern"], "dashed"],
      paint: { "line-dasharray": [3, 2] },
    });
    expect(filtered("routes-line-dotted")).toMatchObject({
      filter: ["==", ["get", "pattern"], "dotted"],
      paint: { "line-dasharray": [0.1, 2.2] },
    });
    expect(filtered("routes-line")).not.toHaveProperty("paint.line-dasharray");
  });

  it("colours every point by its own level, with the legend's five colours and no heat layer", () => {
    const layers = styleWithOurLayers().layers;
    const glow = layers.find((layer) => layer.id === "heatmap-glow");
    const points = layers.find((layer) => layer.id === "heatmap-points");

    expect(layers.some((layer) => layer.type === "heatmap")).toBe(false);
    expect(glow?.type).toBe("circle");
    const colour = JSON.stringify(
      (glow as { paint: Record<string, unknown> }).paint["circle-color"],
    );
    for (const level of ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL"] as const) {
      expect(colour).toContain(LEVEL_STYLES[level].color);
    }
    expect((points as { paint: Record<string, unknown> }).paint["circle-color"]).toEqual(
      (glow as { paint: Record<string, unknown> }).paint["circle-color"],
    );
  });

  it("draws the worse point on top and only the known ones in the glow", () => {
    const glow = styleWithOurLayers().layers.find((layer) => layer.id === "heatmap-glow") as {
      filter: unknown;
      layout: Record<string, unknown>;
    };

    expect(glow.filter).toEqual(["get", "known"]);
    expect(glow.layout["circle-sort-key"]).toEqual(["get", "value"]);
  });

  it("sizes a circle by the grid spacing, doubling with each zoom level", () => {
    const glow = styleWithOurLayers().layers.find((layer) => layer.id === "heatmap-glow");
    const radius = (glow as unknown as { paint: Record<string, unknown[]> }).paint["circle-radius"];
    const [kind, , , firstZoom, first, lastZoom, last] = radius as [
      string,
      unknown,
      unknown,
      number,
      [string, unknown, number],
      number,
      [string, unknown, number],
    ];

    expect(kind).toBe("interpolate");
    expect(first[1]).toEqual(["get", "cell"]);
    expect(last[2] / first[2]).toBeCloseTo(2 ** (lastZoom - firstZoom));
  });

  it("would be caught if one were wrong", () => {
    const style = styleWithOurLayers();
    const points = style.layers.find((layer) => layer.id === "heatmap-points");
    if (points?.type !== "circle") {
      throw new Error("the heatmap points are a circle layer");
    }
    points.paint = {
      "circle-opacity": [
        "case",
        ["get", "known"],
        ["interpolate", ["linear"], ["zoom"], 8, 0, 9, 1],
        0.5,
      ],
    };

    expect(validateStyleMin(style).length).toBeGreaterThan(0);
  });
});
