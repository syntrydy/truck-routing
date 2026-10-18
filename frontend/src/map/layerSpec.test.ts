import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";

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
