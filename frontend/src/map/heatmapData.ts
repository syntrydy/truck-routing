import type { Feature, FeatureCollection, Point } from "geojson";

import type { PlanResponse } from "../api/types.ts";
import { pointPosition, type HeatmapVariable } from "../lib/heatmap.ts";

type Heatmap = PlanResponse["heatmap"];

export interface HeatProperties {
  /** Position on the 0 to 1 colour scale; 0 for unknown points. */
  value: number;
  /** Weight in the heat layer: a floor keeps calm places faintly visible; 0 when unknown. */
  heat: number;
  known: boolean;
}

/** Calm places still count a little, so a safe corridor shows green rather than nothing. */
export const HEAT_FLOOR = 0.1;

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
  return heatmap.frames.map((frame) => {
    const features: Feature<Point, HeatProperties>[] = geometries.map((geometry, index) => {
      const position = pointPosition(variable, frame, index);
      return {
        type: "Feature",
        geometry,
        properties:
          position === null
            ? { value: 0, heat: 0, known: false }
            : { value: position, heat: Math.max(position, HEAT_FLOOR), known: true },
      };
    });
    return { type: "FeatureCollection", features };
  });
}
