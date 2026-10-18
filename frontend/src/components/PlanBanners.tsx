import { memo } from "react";

import type { PlanResponse } from "../api/types.ts";

/** What the API reports as the weather source of the recorded demo. */
const DEMO_SOURCE = "demo";

interface PlanBannersProps {
  plan: PlanResponse;
}

/** What to warn about before the routes: the plan's banner, then its notes. */
export const PlanBanners = memo(function PlanBanners({ plan }: PlanBannersProps) {
  return (
    <div className="banners">
      {plan.meta.weather_source === DEMO_SOURCE && (
        <p className="banner banner--demo" role="status">
          <strong>Demo: a recording, not a live forecast.</strong> These routes and this weather are
          from a real wind storm on I-80 in Wyoming on 17 January 2024, replayed from the moment you
          started the demo. Do not use it to plan a real trip.
        </p>
      )}
      {plan.banner === "NO_SAFE_ROUTE" && (
        <p className="banner banner--danger" role="alert">
          <strong>No safe route.</strong> Every route has a stretch where weather makes travel
          unsafe. The routes are still ranked, but consider leaving at another time.
        </p>
      )}
      {plan.banner === "WEATHER_UNAVAILABLE" && (
        <p className="banner banner--warn" role="status">
          <strong>Weather is unavailable for some places.</strong> Their risk is shown as unknown,
          not as low, so treat those stretches with care.
        </p>
      )}
      {plan.notes.length > 0 && (
        <ul className="banner banner--info" aria-label="Notes about this plan">
          {plan.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
});
