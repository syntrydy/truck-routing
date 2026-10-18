import { memo } from "react";

import type { PlanResponse } from "../api/types.ts";
import { Callout } from "./Callout.tsx";

/** The start of the note about places without weather; the weather banner says the same. */
const MISSING_WEATHER_NOTE = "Weather is unavailable for ";

/** What the API reports as the weather source of the recorded demo. */
const DEMO_SOURCE = "demo";

interface PlanBannersProps {
  plan: PlanResponse;
}

/** What to warn about before the routes: the plan's banner, then its notes. */
export const PlanBanners = memo(function PlanBanners({ plan }: PlanBannersProps) {
  // The weather banner already says that some places have no weather, so its note is left out.
  const notes =
    plan.banner === "WEATHER_UNAVAILABLE"
      ? plan.notes.filter((note) => !note.startsWith(MISSING_WEATHER_NOTE))
      : plan.notes;
  const demo = plan.meta.weather_source === DEMO_SOURCE;
  if (!demo && plan.banner === null && notes.length === 0) {
    return null;
  }
  return (
    <div className="messages">
      {demo && (
        <Callout tone="demo" title="Demo: a recording, not a live forecast" role="status">
          <p>
            A real wind storm on I-80 in Wyoming (17 January 2024), replayed from the moment you
            started the demo. Do not use it to plan a real trip.
          </p>
        </Callout>
      )}
      {plan.banner === "NO_SAFE_ROUTE" && (
        <Callout tone="danger" title="No safe route" role="alert">
          <p>
            Every route has a stretch where weather makes travel unsafe. The routes are still
            ranked, but consider leaving at another time.
          </p>
        </Callout>
      )}
      {plan.banner === "WEATHER_UNAVAILABLE" && (
        <Callout tone="caution" title="Weather is unavailable for some places" role="status">
          <p>Their risk is shown as unknown, not as low, so treat those stretches with care.</p>
        </Callout>
      )}
      {notes.length > 0 && (
        <ul className="footnotes" aria-label="Notes about this plan">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
});
