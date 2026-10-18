import type { Feature, FeatureCollection, LineString, Point } from "geojson";

import type { PlanResponse, RiskLevel } from "../api/types.ts";
import { LEVEL_STYLES } from "../lib/risk.ts";
import { routeLetter, routePattern, type RoutePattern } from "../lib/routeStyle.ts";

type Route = PlanResponse["routes"][number];

export interface RouteSelection {
  selectedId: string | null;
  hoveredId: string | null;
}

export type RouteEmphasis = "selected" | "hovered" | "normal";

export interface RouteProperties {
  id: string;
  label: string;
  rank: number;
  recommended: boolean;
  emphasis: RouteEmphasis;
  /** The route's letter, drawn along it, and the pattern of its line. */
  letter: string;
  pattern: RoutePattern;
  /** Drawing order: higher is drawn on top. */
  order: number;
}

export interface CheckpointProperties {
  routeId: string;
  index: number;
  level: RiskLevel;
  severity: number;
  selected: boolean;
}

const SELECTED_BOOST = 100;
const HOVERED_BOOST = 50;

function emphasisOf(route: Route, selection: RouteSelection): RouteEmphasis {
  if (route.id === selection.selectedId) {
    return "selected";
  }
  return route.id === selection.hoveredId ? "hovered" : "normal";
}

/**
 * The route lines as GeoJSON. Better routes are drawn over worse ones, and a hovered or
 * selected route over all of them, so the one the user is looking at is never hidden.
 */
export function routeFeatures(
  routes: readonly Route[],
  selection: RouteSelection,
): FeatureCollection<LineString, RouteProperties> {
  const features: Feature<LineString, RouteProperties>[] = routes.map((route) => {
    const emphasis = emphasisOf(route, selection);
    const boost =
      emphasis === "selected" ? SELECTED_BOOST : emphasis === "hovered" ? HOVERED_BOOST : 0;
    return {
      type: "Feature",
      geometry: { type: "LineString", coordinates: route.geometry.coordinates },
      properties: {
        id: route.id,
        label: route.label,
        rank: route.rank,
        recommended: route.rank === 1,
        emphasis,
        letter: routeLetter(route.label),
        pattern: routePattern(route.label),
        order: routes.length - route.rank + boost,
      },
    };
  });
  return { type: "FeatureCollection", features };
}

/** The checkpoints of every route as one set of points; the selected route's are marked. */
export function checkpointFeatures(
  routes: readonly Route[],
  selectedId: string | null,
): FeatureCollection<Point, CheckpointProperties> {
  const features: Feature<Point, CheckpointProperties>[] = routes.flatMap((route) =>
    route.checkpoints.map((checkpoint) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [checkpoint.lon, checkpoint.lat] },
      properties: {
        routeId: route.id,
        index: checkpoint.index,
        level: checkpoint.level,
        severity: LEVEL_STYLES[checkpoint.level].severity,
        selected: route.id === selectedId,
      },
    })),
  );
  return { type: "FeatureCollection", features };
}

/** [west, south, east, north] around every route, or `null` when there is nothing to show. */
export function routeBounds(routes: readonly Route[]): [[number, number], [number, number]] | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const route of routes) {
    for (const [lon, lat] of route.geometry.coordinates) {
      if (lon === undefined || lat === undefined) {
        continue;
      }
      west = Math.min(west, lon);
      east = Math.max(east, lon);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
    }
  }
  return Number.isFinite(west)
    ? [
        [west, south],
        [east, north],
      ]
    : null;
}
