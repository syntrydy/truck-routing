import { HEATMAP_VARIABLES, type HeatmapVariable } from "../lib/heatmap.ts";
import { legendEntries } from "../lib/legend.ts";
import { LEVEL_STYLES } from "../lib/risk.ts";

interface HeatmapLegendProps {
  variable: HeatmapVariable;
}

/** What the heatmap colours mean, written out so that colour is not the only way to read them. */
export function HeatmapLegend({ variable }: HeatmapLegendProps) {
  const unit = HEATMAP_VARIABLES.find((candidate) => candidate.id === variable)?.unit ?? "";
  return (
    <ul className="legend" aria-label="What the colours mean">
      {legendEntries(variable, unit).map((entry) => (
        <li key={entry.level}>
          <span
            className="legend__swatch"
            aria-hidden="true"
            style={{ backgroundColor: LEVEL_STYLES[entry.level].color }}
          />
          {entry.text}
        </li>
      ))}
    </ul>
  );
}
