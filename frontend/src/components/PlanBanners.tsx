import { memo } from "react";

import type { PlanResponse } from "../api/types.ts";

interface PlanBannersProps {
  plan: PlanResponse;
}

/** What to warn about before the routes: the plan's banner, then its notes. */
export const PlanBanners = memo(function PlanBanners({ plan }: PlanBannersProps) {
  return (
    <div className="banners">
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
