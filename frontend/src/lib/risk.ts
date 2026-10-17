import type { RiskLevel } from "../api/types.ts";

/** Everything the screens need to show a risk level: words, a colour, and a severity. */
interface LevelStyle {
  label: string;
  /** The heatmap ramp (SPEC section 7): green, yellow, orange, red, purple; unknown is grey. */
  color: string;
  /** 0 (low) to 4 (no travel); -1 when the weather is unknown. */
  severity: number;
}

export const LEVEL_STYLES: Record<RiskLevel, LevelStyle> = {
  UNKNOWN: { label: "Unknown", color: "#7b8794", severity: -1 },
  LOW: { label: "Low", color: "#2e9e4f", severity: 0 },
  MODERATE: { label: "Moderate", color: "#e6c200", severity: 1 },
  HIGH: { label: "High", color: "#f08a00", severity: 2 },
  SEVERE: { label: "Severe", color: "#d62828", severity: 3 },
  NO_TRAVEL: { label: "No travel", color: "#7b2cbf", severity: 4 },
};

export const RISK_LEVELS = Object.keys(LEVEL_STYLES) as RiskLevel[];
