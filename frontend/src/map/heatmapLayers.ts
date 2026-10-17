import type { FeatureCollection, Point } from "geojson";
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

import { LEVEL_STYLES } from "../lib/risk.ts";
import type { HeatProperties } from "./heatmapData.ts";

export const HEATMAP_SOURCE = "heatmap";
export const HEATMAP_GLOW_LAYER = "heatmap-glow";
export const HEATMAP_POINTS_LAYER = "heatmap-points";

const { LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL, UNKNOWN } = LEVEL_STYLES;
const UNKNOWN_COLOR = UNKNOWN.color;

/** The colour scale (0 to 1) as MapLibre stops: green, yellow, orange, red, purple. */
const scaleStops = [
  0,
  LOW.color,
  0.25,
  MODERATE.color,
  0.5,
  HIGH.color,
  0.75,
  SEVERE.color,
  1,
  NO_TRAVEL.color,
];

/** The same ramp over the heat layer's density, transparent where there is nothing. */
const heatColor = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0,
  "rgba(46, 158, 79, 0)",
  0.1,
  "rgba(46, 158, 79, 0.45)",
  0.3,
  MODERATE.color,
  0.5,
  HIGH.color,
  0.75,
  SEVERE.color,
  1,
  NO_TRAVEL.color,
] as unknown as ExpressionSpecification;

const pointColor = [
  "case",
  ["get", "known"],
  ["interpolate", ["linear"], ["get", "value"], ...scaleStops],
  UNKNOWN_COLOR,
] as unknown as ExpressionSpecification;

// The heat fades out as the circles fade in, between these zoom levels (SPEC section 7).
const FADE_START_ZOOM = 8;
const FADE_END_ZOOM = 9.5;
const UNKNOWN_OPACITY = 0.55;

/** The first label layer of the basemap, so that the heatmap goes under the place names. */
function firstSymbolLayerId(map: MapLibreMap): string | undefined {
  return map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
}

/** Adds the heatmap source and its two layers, below the basemap's labels. Safe to call again. */
export function installHeatmapLayers(map: MapLibreMap): void {
  if (map.getSource(HEATMAP_SOURCE) !== undefined) {
    return;
  }
  const before = firstSymbolLayerId(map);
  map.addSource(HEATMAP_SOURCE, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addLayer(
    {
      id: HEATMAP_GLOW_LAYER,
      type: "heatmap",
      source: HEATMAP_SOURCE,
      paint: {
        "heatmap-weight": ["get", "heat"],
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 3, 1.6, 9, 2.4],
        // Wide enough that neighbouring grid points merge into one band at every zoom.
        "heatmap-radius": ["interpolate", ["exponential", 2], ["zoom"], 3, 14, 9, 380],
        "heatmap-color": heatColor,
        "heatmap-opacity": [
          "interpolate",
          ["linear"],
          ["zoom"],
          FADE_START_ZOOM,
          0.9,
          FADE_END_ZOOM,
          0,
        ],
      },
    },
    before,
  );
  // Unknown places stay visible as grey dots at every zoom: never drawn as calm.
  map.addLayer(
    {
      id: HEATMAP_POINTS_LAYER,
      type: "circle",
      source: HEATMAP_SOURCE,
      paint: {
        "circle-color": pointColor,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 3, 9, 7, 12, 16],
        // Zoom has to be the outermost expression, so the known/unknown choice sits inside it.
        "circle-opacity": [
          "interpolate",
          ["linear"],
          ["zoom"],
          FADE_START_ZOOM,
          ["case", ["get", "known"], 0, UNKNOWN_OPACITY],
          FADE_END_ZOOM,
          ["case", ["get", "known"], 0.85, UNKNOWN_OPACITY],
        ],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 9, 0, 11, 1],
      },
    },
    before,
  );
}

/** Replaces what the heatmap layers draw with one hour's frame. */
export function setHeatmapFrame(
  map: MapLibreMap,
  frame: FeatureCollection<Point, HeatProperties>,
): void {
  void map.getSource<GeoJSONSource>(HEATMAP_SOURCE)?.setData(frame);
}
