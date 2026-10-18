/**
 * Moves focus to `target` only if focus has been lost, meaning it is on the page body or nowhere:
 * what happens when the element that had it is hidden. Focus that is somewhere real stays put.
 */
export function focusIfLost(target: HTMLElement | null, doc: Document = document): void {
  const active = doc.activeElement;
  if (target !== null && (active === null || active === doc.body)) {
    target.focus();
  }
}
