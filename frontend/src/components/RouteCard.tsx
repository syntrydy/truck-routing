import type { PlanResponse } from "../api/types.ts";
import { formatDuration, formatMiles } from "../lib/format.ts";
import { LEVEL_STYLES } from "../lib/risk.ts";
import { routePattern, SWATCH_DASH } from "../lib/routeStyle.ts";
import { RiskBar } from "./RiskBar.tsx";

type Route = PlanResponse["routes"][number];

interface RouteCardProps {
  route: Route;
  recommended: boolean;
  /** Why this route was recommended; only given for the recommended route. */
  reason: string | null;
  selected: boolean;
  hovered: boolean;
  onSelect: () => void;
  onHover: (hovering: boolean) => void;
}

/**
 * One route: how long and how far, how risky, and a way to pick it. Only the title is a
 * button, so the card's other content stays ordinary text; a stylesheet rule stretches the
 * button over the whole card, so the whole card can be clicked.
 */
export function RouteCard({
  route,
  recommended,
  reason,
  selected,
  hovered,
  onSelect,
  onHover,
}: RouteCardProps) {
  const { summary } = route;
  const classes = [
    "route-card",
    selected && "route-card--selected",
    hovered && "route-card--hovered",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <li className={classes}>
      <h3 className="route-card__head">
        <span className="route-card__rank">
          <span className="visually-hidden">Rank </span>
          {route.rank}
        </span>
        <svg className="route-card__swatch" viewBox="0 0 32 6" aria-hidden="true">
          <line
            x1="2"
            y1="3"
            x2="30"
            y2="3"
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={SWATCH_DASH[routePattern(route.label)]}
          />
        </svg>
        <button
          type="button"
          className="route-card__button"
          aria-pressed={selected}
          onClick={onSelect}
          onMouseEnter={() => {
            onHover(true);
          }}
          onMouseLeave={() => {
            onHover(false);
          }}
          onFocus={() => {
            onHover(true);
          }}
          onBlur={() => {
            onHover(false);
          }}
        >
          {route.label}
        </button>
        {recommended && <span className="badge badge--good">Recommended</span>}
        {selected && <span className="badge">Shown on map</span>}
      </h3>
      <p className="route-card__facts">
        {formatDuration(route.duration_s)} · {formatMiles(route.distance_mi)} · Worst:{" "}
        {LEVEL_STYLES[summary.worst_level].label}
      </p>
      {reason !== null && <p className="route-card__reason">{reason}</p>}
      {summary.low_confidence && (
        <p className="route-card__warning">
          <span className="badge badge--warn">
            Low confidence: weather is missing for part of this route
          </span>
        </p>
      )}
      <RiskBar summary={summary} />
    </li>
  );
}
