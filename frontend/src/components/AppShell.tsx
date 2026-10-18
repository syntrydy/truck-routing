import { useId, type ReactNode, type Ref } from "react";

import { TruckIcon } from "./icons.tsx";

interface AppShellProps {
  /** The name of the app: the page's heading, kept in the page even when the sheet is folded. */
  title: string;
  /** The form and the route cards. */
  panel: ReactNode;
  map: ReactNode;
  /** The forecast slider along the bottom. */
  slider: ReactNode;
  /** On a narrow screen the panel is a bottom sheet; whether it is open. Ignored on a wide one. */
  sheetOpen: boolean;
  onSheetOpenChange: (open: boolean) => void;
  /** What the closed sheet's bar says, such as the best route; "Trip details" without one. */
  sheetSummary?: string | null;
  /** The sheet's bar, so that the page can give it focus. */
  toggleRef?: Ref<HTMLButtonElement>;
}

/**
 * The page layout (SPEC section 7): a left panel, the map, and the slider under the map. On a
 * narrow screen the panel becomes a sheet under the map that folds down to a bar, so the map
 * can use the screen.
 */
export function AppShell({
  title,
  panel,
  map,
  slider,
  sheetOpen,
  onSheetOpenChange,
  sheetSummary = null,
  toggleRef,
}: AppShellProps) {
  const contentId = useId();
  return (
    <div className={sheetOpen ? "shell" : "shell shell--collapsed"}>
      <aside className="shell__panel" aria-label="Trip planner">
        <h1 className="shell__title">
          <span className="brand-mark">
            <TruckIcon />
          </span>
          {title}
        </h1>
        <button
          ref={toggleRef}
          type="button"
          className="sheet-toggle"
          aria-expanded={sheetOpen}
          aria-controls={contentId}
          onClick={() => {
            onSheetOpenChange(!sheetOpen);
          }}
        >
          <span className="sheet-toggle__grip" aria-hidden="true" />
          <span className="sheet-toggle__text">{sheetSummary ?? "Trip details"}</span>
          <span aria-hidden="true" className="sheet-toggle__hint">
            {sheetOpen ? "▾" : "▴"}{" "}
            <span className="sheet-toggle__word">{sheetOpen ? "Hide" : "Show"}</span>
          </span>
        </button>
        <div id={contentId} className="shell__panel-content">
          {panel}
        </div>
      </aside>
      <main className="shell__map">{map}</main>
      <section className="shell__slider" aria-label="Forecast">
        {slider}
      </section>
    </div>
  );
}
