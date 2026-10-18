/**
 * The screens that get the phone layout: the map on top with the trip sheet below. A phone, and
 * a tablet held upright, where a side panel would leave the map too narrow. The same rule is the
 * media query that switches the layout in `styles.css`; keep the two together.
 */
export const SHEET_LAYOUT_QUERY =
  "(max-width: 50rem), (max-width: 64rem) and (orientation: portrait)";

/** A screen with little height, such as a phone held sideways; `styles.css` has the same rule. */
export const SHORT_SCREEN_QUERY = "(max-height: 32rem)";

const matches = (query: string) =>
  typeof window.matchMedia === "function" && window.matchMedia(query).matches;

/** Whether the screen gets the phone layout; `false` where the browser cannot say. */
export function isSheetLayout(): boolean {
  return matches(SHEET_LAYOUT_QUERY);
}

/**
 * Whether there is too little room for everything at once: a phone, a tablet held upright, or a
 * screen with little height. The map's credit then folds behind a button and the forecast
 * control's explanation starts folded.
 */
export function isCramped(): boolean {
  return matches(SHEET_LAYOUT_QUERY) || matches(SHORT_SCREEN_QUERY);
}
