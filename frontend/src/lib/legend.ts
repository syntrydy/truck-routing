import { BAND_STARTS, type HeatmapVariable } from "./heatmap.ts";
import { LEVEL_STYLES } from "./risk.ts";
import type { RiskLevel } from "../api/types.ts";

export interface LegendEntry {
  level: RiskLevel;
  /** What the colour stands for, in words. */
  text: string;
}

const KNOWN: readonly RiskLevel[] = ["LOW", "MODERATE", "HIGH", "SEVERE", "NO_TRAVEL"];

const range = (from: number | null, to: number | null, unit: string): string => {
  if (from === null && to !== null) {
    return `under ${String(to)} ${unit}`;
  }
  return to === null
    ? `${String(from)} ${unit} or more`
    : `${String(from)} to ${String(to)} ${unit}`;
};

/** What each colour means for `variable`, from calm to worst, then the grey for unknown. */
export function legendEntries(variable: HeatmapVariable, unit: string): LegendEntry[] {
  const unknown: LegendEntry = { level: "UNKNOWN", text: "Unknown: no forecast" };
  if (variable === "risk") {
    return [...KNOWN.map((level) => ({ level, text: LEVEL_STYLES[level].label })), unknown];
  }
  const starts = BAND_STARTS[variable];
  return [
    ...KNOWN.map((level, index) => ({
      level,
      text: `${LEVEL_STYLES[level].label}: ${range(starts[index - 1] ?? null, starts[index] ?? null, unit)}`,
    })),
    unknown,
  ];
}
