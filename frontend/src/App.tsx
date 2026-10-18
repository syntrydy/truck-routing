import { useRef, useState } from "react";

import type { PlanRequest } from "./api/types.ts";
import { useWarmUp } from "./api/useWarmUp.ts";
import { AppShell } from "./components/AppShell.tsx";
import { PlanBanners } from "./components/PlanBanners.tsx";
import { PlanStatus } from "./components/PlanStatus.tsx";
import { ServerStatus } from "./components/ServerStatus.tsx";
import { RouteCards } from "./components/RouteCards.tsx";
import { TripForm } from "./components/TripForm.tsx";
import { ForecastSlider } from "./components/ForecastSlider.tsx";
import { useForecast } from "./hooks/useForecast.ts";
import { usePlan } from "./hooks/usePlan.ts";
import { focusIfLost } from "./lib/focus.ts";
import { formatDuration } from "./lib/format.ts";
import { MapView } from "./map/MapView.tsx";

export function App() {
  const warmUp = useWarmUp();
  const plan = usePlan();
  const [planned, setPlanned] = useState<PlanRequest | null>(null);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(true);
  const toggleRef = useRef<HTMLButtonElement>(null);

  const forecast = useForecast(plan.data ?? null);
  const routes = plan.data?.routes ?? [];
  // The user's pick if it is on screen, otherwise the recommended route.
  const selectedId = routes.some((route) => route.id === chosenId)
    ? chosenId
    : (plan.data?.recommended_route_id ?? routes[0]?.id ?? null);

  const planTrip = (request: PlanRequest) => {
    setPlanned(request);
    setChosenId(null);
    // On a phone, fold the sheet away to show the map when the plan arrives; open it for an error.
    plan.mutate(request, {
      onSuccess: () => {
        setSheetOpen(false);
        // The results heading takes focus when it is on screen; on a phone it is folded away
        // with the sheet, so focus goes to the sheet's bar instead of being lost.
        // The browser only drops focus from a hidden element once it has laid the page out, so
        // look again two frames on.
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            focusIfLost(toggleRef.current);
          });
        });
      },
      onError: () => {
        setSheetOpen(true);
      },
    });
  };
  const data = plan.data;
  const best = data?.routes.find((route) => route.id === data.recommended_route_id);
  const summary =
    best === undefined ? null : `${best.label} · ${formatDuration(best.duration_s)} · Trip details`;
  const hasNothingYet = plan.data === undefined && !plan.isPending && !plan.isError;

  return (
    <AppShell
      title="Weather-Aware Truck Routing"
      toggleRef={toggleRef}
      sheetOpen={sheetOpen}
      onSheetOpenChange={setSheetOpen}
      sheetSummary={summary}
      panel={
        <>
          <p>Pick a route, check the weather along it, and drive the safest one.</p>
          <ServerStatus waking={warmUp.isPending} failed={warmUp.isError} />
          <TripForm planned={planned} onSubmit={planTrip} />
          <PlanStatus
            pending={plan.isPending}
            error={plan.error}
            plan={plan.data ?? null}
            onRetry={() => {
              if (planned !== null) {
                planTrip(planned);
              }
            }}
          />
          {hasNothingYet && (
            <p className="empty-state">
              Choose where you start and where you are going. You will see up to three routes,
              ranked by weather risk, and a forecast for the next 48 hours along them.
            </p>
          )}
          {plan.data !== undefined && (
            <>
              <PlanBanners plan={plan.data} />
              <RouteCards
                plan={plan.data}
                selectedId={selectedId}
                hoveredId={hoveredId}
                onSelect={setChosenId}
                onHover={setHoveredId}
              />
            </>
          )}
        </>
      }
      map={
        <MapView
          plan={plan.data ?? null}
          selection={{ selectedId, hoveredId }}
          onSelectRoute={setChosenId}
          onHoverRoute={setHoveredId}
          forecast={{ frames: forecast.frames, hour: forecast.hour }}
        />
      }
      slider={
        plan.data === undefined ? (
          <p>The forecast slider appears once a trip is planned.</p>
        ) : (
          <ForecastSlider
            startIso={plan.data.heatmap.start}
            hour={forecast.hour}
            maxHour={forecast.maxHour}
            playing={forecast.playing}
            variable={forecast.variable}
            onHourChange={forecast.setHour}
            onTogglePlay={forecast.togglePlay}
            onVariableChange={forecast.setVariable}
          />
        )
      }
    />
  );
}
