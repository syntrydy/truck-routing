import type { PlanResponse } from "../api/types.ts";
import { LEVEL_STYLES } from "../lib/risk.ts";

type Checkpoint = PlanResponse["routes"][number]["checkpoints"][number];

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
