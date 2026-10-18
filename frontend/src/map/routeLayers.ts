import type { FeatureCollection } from "geojson";
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

import type { PlanResponse } from "../api/types.ts";
import { LEVEL_STYLES, RISK_LEVELS } from "../lib/risk.ts";
import { MAP_DASH, type RoutePattern } from "../lib/routeStyle.ts";
import {
  checkpointFeatures,
  routeBounds,
  routeFeatures,
  type RouteSelection,
} from "./routeData.ts";

type Route = PlanResponse["routes"][number];

export const ROUTES_SOURCE = "routes";
export const ROUTES_CASING_LAYER = "routes-casing";
export const ROUTES_LINE_LAYER = "routes-line";
export const ROUTES_DASHED_LAYER = "routes-line-dashed";
export const ROUTES_DOTTED_LAYER = "routes-line-dotted";
export const ROUTES_LABEL_LAYER = "routes-label";
/** The layers that draw the route lines, one for each pattern: a pattern cannot vary by feature. */
export const ROUTES_LINE_LAYERS = [ROUTES_LINE_LAYER, ROUTES_DASHED_LAYER, ROUTES_DOTTED_LAYER];
export const CHECKPOINTS_SOURCE = "checkpoints";
export const CHECKPOINTS_LAYER = "checkpoints";

const empty = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });
const FIT_PADDING = 48;
const FIT_MAX_ZOOM = 11;
const FIT_DURATION_MS = 700;

/** A value for each emphasis of a route: selected, hovered, and the rest. */
const byEmphasis = <T extends string | number>(
  selected: T,
  hovered: T,
  normal: T,
): ExpressionSpecification => [
  "match",
  ["get", "emphasis"],
  "selected",
  selected,
  "hovered",
  hovered,
  normal,
];

/** The colour of a checkpoint from its level, for MapLibre to evaluate for each point. */
// One label/colour pair per level: MapLibre's type cannot express a "match" of that length.
const levelColor = [
  "match",
  ["get", "level"],
  ...RISK_LEVELS.flatMap((level) => [level, LEVEL_STYLES[level].color]),
  LEVEL_STYLES.UNKNOWN.color,
] as unknown as ExpressionSpecification;

/** Adds the sources and layers for routes and checkpoints, once. Safe to call again. */
export function installRouteLayers(map: MapLibreMap): void {
  if (map.getSource(ROUTES_SOURCE) !== undefined) {
    return;
  }
  map.addSource(ROUTES_SOURCE, { type: "geojson", data: empty() });
  map.addSource(CHECKPOINTS_SOURCE, { type: "geojson", data: empty() });

  // A white outline under every line keeps it readable over any basemap colour.
  map.addLayer({
    id: ROUTES_CASING_LAYER,
    type: "line",
    source: ROUTES_SOURCE,
    layout: { "line-cap": "round", "line-join": "round", "line-sort-key": ["get", "order"] },
    paint: { "line-color": "#ffffff", "line-width": byEmphasis(12, 10, 8) },
  });
  const lines: [string, RoutePattern][] = [
    [ROUTES_LINE_LAYER, "solid"],
    [ROUTES_DASHED_LAYER, "dashed"],
    [ROUTES_DOTTED_LAYER, "dotted"],
  ];
  for (const [id, pattern] of lines) {
    map.addLayer({
      id,
      type: "line",
      source: ROUTES_SOURCE,
      filter: ["==", ["get", "pattern"], pattern],
      layout: { "line-cap": "round", "line-join": "round", "line-sort-key": ["get", "order"] },
      paint: {
        "line-color": byEmphasis("#1a3d7c", "#3b6fd0", "#6b7c93"),
        "line-width": byEmphasis(8, 6, 4),
        ...(pattern === "solid" ? {} : { "line-dasharray": MAP_DASH[pattern] }),
      },
    });
  }
  // The route's letter along its line, over a white halo; the selected route's wins a clash.
  map.addLayer({
    id: ROUTES_LABEL_LAYER,
    type: "symbol",
    source: ROUTES_SOURCE,
    layout: {
      "symbol-placement": "line",
      "symbol-spacing": 320,
      "symbol-sort-key": ["-", 0, ["get", "order"]],
      "text-field": ["get", "letter"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 15,
      "text-padding": 8,
      "text-keep-upright": true,
    },
    paint: {
      "text-color": byEmphasis("#1a3d7c", "#1a3d7c", "#3d4a5c"),
      "text-halo-color": "#ffffff",
      "text-halo-width": 2.5,
    },
  });
  // Level is also in the size of the dot (worse is bigger), so it does not rest on colour alone.
  map.addLayer({
    id: CHECKPOINTS_LAYER,
    type: "circle",
    source: CHECKPOINTS_SOURCE,
    layout: { "circle-sort-key": ["get", "severity"] },
    paint: {
      "circle-color": levelColor,
      "circle-radius": [
        "+",
        ["case", ["get", "selected"], 3, 0],
        ["+", 5, ["*", 1.2, ["get", "severity"]]],
      ],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": ["case", ["get", "selected"], 2, 1],
      "circle-opacity": ["case", ["get", "selected"], 1, 0.6],
    },
  });
}

/** Replaces what the route and checkpoint layers draw. */
export function setRouteData(
  map: MapLibreMap,
  routes: readonly Route[],
  selection: RouteSelection,
): void {
  void map.getSource<GeoJSONSource>(ROUTES_SOURCE)?.setData(routeFeatures(routes, selection));
  void map
    .getSource<GeoJSONSource>(CHECKPOINTS_SOURCE)
    ?.setData(checkpointFeatures(routes, selection.selectedId));
}

/** Moves the view to show every route, without animation for people who ask for less motion. */
export function fitToRoutes(map: MapLibreMap, routes: readonly Route[]): void {
  const bounds = routeBounds(routes);
  if (bounds === null) {
    return;
  }
  const reduceMotion =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  map.fitBounds(bounds, {
    padding: FIT_PADDING,
    maxZoom: FIT_MAX_ZOOM,
    duration: reduceMotion ? 0 : FIT_DURATION_MS,
  });
}
