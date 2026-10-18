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

const pointColor = [
  "case",
  ["get", "known"],
  ["interpolate", ["linear"], ["get", "value"], ...scaleStops],
  UNKNOWN_COLOR,
] as unknown as ExpressionSpecification;

/**
 * The radius of a point's soft circle: `GLOW_REACH` of the grid spacing at every zoom, so that
 * neighbours join up into a band. A degree is 256 * 2^zoom / 360 pixels wide, so the radius
 * doubles with each zoom level; an exponential interpolation of base 2 between two stops that
 * differ by that factor is exact between them.
 */
const GLOW_REACH = 1.6;
const GLOW_FIRST_ZOOM = 3;
const GLOW_LAST_ZOOM = 10;
const PIXELS_PER_DEGREE_AT_ZOOM_0 = 256 / 360;
const pixelsPerCellDegree = (zoom: number) => GLOW_REACH * PIXELS_PER_DEGREE_AT_ZOOM_0 * 2 ** zoom;
const glowRadius = [
  "interpolate",
  ["exponential", 2],
  ["zoom"],
  GLOW_FIRST_ZOOM,
  ["*", ["get", "cell"], pixelsPerCellDegree(GLOW_FIRST_ZOOM)],
  GLOW_LAST_ZOOM,
  ["*", ["get", "cell"], pixelsPerCellDegree(GLOW_LAST_ZOOM)],
] as unknown as ExpressionSpecification;
const GLOW_BLUR = 0.8;
const GLOW_OPACITY = 0.7;

// The glow fades out as the crisp circles fade in, between these zoom levels (SPEC section 7).
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
  // One soft circle per point in the point's own colour, so a colour on the map is a level on
  // the legend. (A heatmap layer colours by the density of points, which adds Moderate points up
  // to red.) The worse point is drawn on top where circles meet, and none changes the other's
  // colour.
  map.addLayer(
    {
      id: HEATMAP_GLOW_LAYER,
      type: "circle",
      source: HEATMAP_SOURCE,
      filter: ["get", "known"],
      layout: { "circle-sort-key": ["get", "value"] },
      paint: {
        "circle-color": pointColor,
        "circle-radius": glowRadius,
        "circle-blur": GLOW_BLUR,
        "circle-opacity": [
          "interpolate",
          ["linear"],
          ["zoom"],
          FADE_START_ZOOM,
          GLOW_OPACITY,
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
