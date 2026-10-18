import type { Feature, FeatureCollection, Point } from "geojson";

import type { PlanResponse } from "../api/types.ts";
import { pointPosition, type HeatmapVariable } from "../lib/heatmap.ts";

type Heatmap = PlanResponse["heatmap"];

export interface HeatProperties {
  /** Position on the 0 to 1 colour scale; 0 for unknown points. */
  value: number;
  known: boolean;
  /** The grid spacing in degrees, which sizes the point's circle so that neighbours join up. */
  cell: number;
}

/** The spacing assumed for a grid with a single row of points: the weather cache's resolution. */
const DEFAULT_CELL_DEG = 0.1;

/**
 * The spacing of the grid in degrees: the smallest step between its rows of latitude. The grid
 * is a lattice, so that is the distance between neighbours however its mask cuts it.
 */
export function cellSizeDeg(points: Heatmap["points"]): number {
  const latitudes = [...new Set(points.map(([lat]) => lat ?? 0))].sort((a, b) => a - b);
  let step = Infinity;
  for (let index = 1; index < latitudes.length; index += 1) {
    step = Math.min(step, (latitudes[index] ?? 0) - (latitudes[index - 1] ?? 0));
  }
  return Number.isFinite(step) && step > 0 ? step : DEFAULT_CELL_DEG;
}

/**
 * One set of points for every hour of the heatmap, for `variable`. The points are the same in
 * every frame, so the geometry is made once and shared; only the properties change. Built
 * once per plan and variable, then the slider only picks one.
 */
export function buildHeatmapFrames(
  heatmap: Heatmap,
  variable: HeatmapVariable,
): FeatureCollection<Point, HeatProperties>[] {
  const geometries: Point[] = heatmap.points.map(([lat, lon]) => ({
    type: "Point",
    coordinates: [lon ?? 0, lat ?? 0],
  }));
  const cell = cellSizeDeg(heatmap.points);
  return heatmap.frames.map((frame) => {
    const features: Feature<Point, HeatProperties>[] = geometries.map((geometry, index) => {
      const position = pointPosition(variable, frame, index);
      return {
        type: "Feature",
        geometry,
        properties:
          position === null
            ? { value: 0, known: false, cell }
            : { value: position, known: true, cell },
      };
    });
    return { type: "FeatureCollection", features };
  });
}
