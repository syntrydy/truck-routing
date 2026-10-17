import type { PlanResponse } from "../api/types.ts";

type Heatmap = PlanResponse["heatmap"];
export type HeatmapFrame = Heatmap["frames"][number];

export type HeatmapVariable = "risk" | "wind" | "rain" | "snow";

export const HEATMAP_VARIABLES: readonly {
  id: HeatmapVariable;
  label: string;
  unit: string;
}[] = [
  { id: "risk", label: "Risk", unit: "" },
  { id: "wind", label: "Wind", unit: "mph" },
  { id: "rain", label: "Rain", unit: "in/hr" },
  { id: "snow", label: "Snow", unit: "in/hr" },
];

/**
 * Where each band starts, for the values the SPEC's risk table (section 4.5) is made of:
 * Moderate, High, Severe and No travel. Wind is sustained speed in mph, rain and snow are
 * inches per hour.
 */
export const BAND_STARTS: Record<
  Exclude<HeatmapVariable, "risk">,
  readonly [number, number, number, number]
> = {
  wind: [25, 35, 45, 55],
  rain: [0.1, 0.25, 0.5, 1],
  snow: [0.5, 1, 2, 3],
};

/** A reading on the shared 0 to 1 colour scale: 0 is calm, 1 is where travel stops. */
export type Position = number;

const LEVEL_COUNT = 4; // the steps from LOW to NO_TRAVEL

/**
 * Places a weather reading on the colour scale so that the colours mean the same for every
 * variable: the start of Moderate is a quarter of the way, the start of No travel is the end.
 * Between the starts the scale is linear; beyond the last it stays at 1.
 */
export function bandPosition(value: number, starts: readonly number[]): Position {
  if (value <= 0) {
    return 0;
  }
  let lower = 0;
  for (const [step, start] of starts.entries()) {
    if (value < start) {
      return (step + (value - lower) / (start - lower)) / LEVEL_COUNT;
    }
    lower = start;
  }
  return 1;
}

/** What the map shows for one point: its position on the scale, or `null` if unknown. */
export function pointPosition(
  variable: HeatmapVariable,
  frame: HeatmapFrame,
  index: number,
): Position | null {
  if (variable === "risk") {
    const level = frame.risk[index];
    return level === undefined || level < 0 ? null : level / LEVEL_COUNT;
  }
  const reading = frame[variable][index];
  return reading === undefined || reading === null
    ? null
    : bandPosition(reading, BAND_STARTS[variable]);
}
