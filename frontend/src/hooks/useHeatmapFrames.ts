import { useMemo } from "react";

import type { PlanResponse } from "../api/types.ts";
import type { HeatmapVariable } from "../lib/heatmap.ts";
import { buildHeatmapFrames } from "../map/heatmapData.ts";

/** The frames of the plan's heatmap for one variable, made once and kept until either changes. */
export function useHeatmapFrames(plan: PlanResponse | null, variable: HeatmapVariable) {
  const heatmap = plan?.heatmap;
  return useMemo(
    () => (heatmap === undefined ? null : buildHeatmapFrames(heatmap, variable)),
    [heatmap, variable],
  );
}
