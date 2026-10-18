/**
 * How each route is drawn, so that routes differ by more than colour: Route A is a solid line,
 * Route B dashed and Route C dotted. Routes are lettered by speed (A is the fastest), so the
 * look of a route does not change when the ranking or the selection does.
 */
export type RoutePattern = "solid" | "dashed" | "dotted";

const PATTERNS: readonly RoutePattern[] = ["solid", "dashed", "dotted"];

/** The letter of a label such as "Route B": `B`. */
export function routeLetter(label: string): string {
  return label.trim().slice(-1).toUpperCase();
}

/** The pattern of the route with this label; a letter past C starts again with solid. */
export function routePattern(label: string): RoutePattern {
  const index = routeLetter(label).charCodeAt(0) - "A".charCodeAt(0);
  return PATTERNS[((index % PATTERNS.length) + PATTERNS.length) % PATTERNS.length] ?? "solid";
}

/** `line-dasharray` for MapLibre, in multiples of the line width; solid has none. */
export const MAP_DASH: Record<Exclude<RoutePattern, "solid">, number[]> = {
  dashed: [3, 2],
  dotted: [0.1, 2.2],
};

/** `stroke-dasharray` for the swatch on a route card, in pixels. */
export const SWATCH_DASH: Record<RoutePattern, string | undefined> = {
  solid: undefined,
  dashed: "7 4",
  dotted: "0.1 5",
};
