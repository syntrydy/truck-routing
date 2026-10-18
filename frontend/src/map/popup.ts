import type { PlanResponse } from "../api/types.ts";
import { formatDuration, formatMiles } from "../lib/format.ts";
import { LEVEL_STYLES } from "../lib/risk.ts";

type Route = PlanResponse["routes"][number];
type Checkpoint = Route["checkpoints"][number];

const UNAVAILABLE = "not available";

/** The ETA as the reader's local time with its zone, e.g. `Sun, Oct 18, 2:00 PM CDT`. */
export function formatEta(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(iso));
}

/**
 * A route in one line, with the figures of its card: `Route A · 9 h · 505 mi · 75 mi No travel`,
 * or `Route B · 9 h 57 min · 503 mi · Worst: Low` when nothing is worse than Low.
 */
export function routeSummaryText(route: Route): string {
  const { worst_level: worst, miles_by_level: miles } = route.summary;
  const atWorst = miles[worst] ?? 0;
  const risk =
    worst === "LOW" || worst === "UNKNOWN" || atWorst <= 0
      ? `Worst: ${LEVEL_STYLES[worst].label}`
      : `${formatMiles(atWorst)} ${LEVEL_STYLES[worst].label}`;
  return [route.label, formatDuration(route.duration_s), formatMiles(route.distance_mi), risk].join(
    " · ",
  );
}

/** The label shown beside the pointer on a route line, from text nodes only. */
export function buildRouteSummary(route: Route, doc: Document = document): HTMLElement {
  const root = doc.createElement("p");
  root.className = "route-tip";
  root.textContent = routeSummaryText(route);
  return root;
}

function measure(value: number | null, unit: string): string {
  return value === null ? UNAVAILABLE : `${String(value)} ${unit}`;
}

/**
 * The popup of a checkpoint, built with text nodes only: what the server says is shown, never
 * parsed as markup.
 */
export function buildCheckpointPopup(
  checkpoint: Checkpoint,
  routeLabel: string,
  doc: Document = document,
): HTMLElement {
  const root = doc.createElement("div");
  root.className = "popup";

  const heading = doc.createElement("h3");
  heading.textContent = `${routeLabel}, mile ${String(checkpoint.mile)}`;
  const level = doc.createElement("p");
  level.className = "popup__level";
  level.textContent = `Risk: ${LEVEL_STYLES[checkpoint.level].label}`;
  root.append(heading, level);

  const facts = doc.createElement("dl");
  const rows: [string, string][] = [
    ["Arrival", formatEta(checkpoint.eta)],
    ["Wind", measure(checkpoint.wind_mph, "mph")],
    ["Gusts", measure(checkpoint.gust_mph, "mph")],
    ["Rain", measure(checkpoint.rain_in_hr, "in/hr")],
    ["Snow", measure(checkpoint.snow_in_hr, "in/hr")],
  ];
  for (const [name, value] of rows) {
    const term = doc.createElement("dt");
    term.textContent = name;
    const description = doc.createElement("dd");
    description.textContent = value;
    facts.append(term, description);
  }
  root.append(facts);

  if (checkpoint.reasons.length > 0) {
    const reasons = doc.createElement("ul");
    for (const reason of checkpoint.reasons) {
      const item = doc.createElement("li");
      item.textContent = reason;
      reasons.append(item);
    }
    root.append(reasons);
  }
  return root;
}
