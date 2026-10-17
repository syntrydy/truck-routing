import type { ReactNode } from "react";

interface AppShellProps {
  /** The form and the route cards. */
  panel: ReactNode;
  map: ReactNode;
  /** The forecast slider along the bottom. */
  slider: ReactNode;
}

/** The page layout (SPEC section 7): a left panel, the map, and the slider under the map. */
export function AppShell({ panel, map, slider }: AppShellProps) {
  return (
    <div className="shell">
      <aside className="shell__panel" aria-label="Trip planner">
        {panel}
      </aside>
      <main className="shell__map">{map}</main>
      <section className="shell__slider" aria-label="Forecast">
        {slider}
      </section>
    </div>
  );
}
