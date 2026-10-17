import { formatMiles } from "../lib/format.ts";
import { LEVEL_STYLES } from "../lib/risk.ts";
import { barSegments, segmentLabel } from "../lib/riskBar.ts";
import type { PlanResponse } from "../api/types.ts";

interface RiskBarProps {
  summary: PlanResponse["routes"][number]["summary"];
}

/**
 * A route's miles by risk level as a stacked bar. The list under it says the same in words,
 * so the colours are never the only way to read it; the bar itself is hidden from screen readers.
 */
export function RiskBar({ summary }: RiskBarProps) {
  const segments = barSegments(summary);
  if (segments.length === 0) {
    return null;
  }
  return (
    <div className="risk-bar">
      <div className="risk-bar__track" aria-hidden="true">
        {segments.map((segment) => (
          <span
            key={segment.level}
            className="risk-bar__segment"
            style={{
              width: `${String(segment.percent)}%`,
              backgroundColor: LEVEL_STYLES[segment.level].color,
            }}
          />
        ))}
      </div>
      <ul className="risk-bar__legend" aria-label="Miles by risk level">
        {segments.map((segment) => (
          <li key={segment.level}>
            <span
              className="risk-bar__swatch"
              aria-hidden="true"
              style={{ backgroundColor: LEVEL_STYLES[segment.level].color }}
            />
            {segmentLabel(segment, formatMiles)}
          </li>
        ))}
      </ul>
    </div>
  );
}
