import type { PlanResponse } from "../api/types.ts";

type Checkpoint = PlanResponse["routes"][number]["checkpoints"][number];

/**
 * Where the truck is at `whenMs`, as [longitude, latitude]: on the straight line between the
 * two checkpoints whose arrival times surround that moment. Before the first it is waiting at
 * the start; after the last it has arrived. `null` when the route has no checkpoints.
 */
export function truckPosition(
  checkpoints: readonly Checkpoint[],
  whenMs: number,
): [number, number] | null {
  const first = checkpoints[0];
  const last = checkpoints[checkpoints.length - 1];
  if (first === undefined || last === undefined) {
    return null;
  }
  if (whenMs <= Date.parse(first.eta)) {
    return [first.lon, first.lat];
  }
  for (let index = 1; index < checkpoints.length; index += 1) {
    const from = checkpoints[index - 1];
    const to = checkpoints[index];
    if (from === undefined || to === undefined) {
      continue;
    }
    const start = Date.parse(from.eta);
    const end = Date.parse(to.eta);
    if (whenMs <= end) {
      const share = end === start ? 1 : (whenMs - start) / (end - start);
      return [from.lon + (to.lon - from.lon) * share, from.lat + (to.lat - from.lat) * share];
    }
  }
  return [last.lon, last.lat];
}

/** The truck marker's element: a small truck drawn in SVG, labelled for assistive technology. */
export function buildTruckElement(doc: Document = document): HTMLElement {
  const element = doc.createElement("div");
  element.className = "truck";
  element.setAttribute("role", "img");
  element.setAttribute("aria-label", "Truck position at the chosen hour");
  const svgNamespace = "http://www.w3.org/2000/svg";
  const svg = doc.createElementNS(svgNamespace, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "22");
  svg.setAttribute("height", "22");
  svg.setAttribute("aria-hidden", "true");
  const body = doc.createElementNS(svgNamespace, "path");
  body.setAttribute("d", "M2 6h12v9H2zM14 9h4l3 3v3h-7z");
  body.setAttribute("fill", "currentColor");
  const wheels = doc.createElementNS(svgNamespace, "path");
  wheels.setAttribute("d", "M6 17.5a2 2 0 1 0 .01 0M17 17.5a2 2 0 1 0 .01 0");
  wheels.setAttribute("fill", "#ffffff");
  wheels.setAttribute("stroke", "currentColor");
  wheels.setAttribute("stroke-width", "1.5");
  svg.append(body, wheels);
  element.append(svg);
  return element;
}
