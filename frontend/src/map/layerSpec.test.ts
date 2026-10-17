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
      "checkpoints",
      "heatmap-glow",
      "heatmap-points",
    ]);
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
