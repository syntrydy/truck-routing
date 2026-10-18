import { useCallback, useId, useMemo, useRef, useState } from "react";

import type { PlanRequest } from "./api/types.ts";
import { useWarmUp } from "./api/useWarmUp.ts";
import { AppShell } from "./components/AppShell.tsx";
import { PlanBanners } from "./components/PlanBanners.tsx";
import { PlanStatus } from "./components/PlanStatus.tsx";
import { RankingTable } from "./components/RankingTable.tsx";
import { ServerStatus } from "./components/ServerStatus.tsx";
import { RouteCards } from "./components/RouteCards.tsx";
import { TripForm } from "./components/TripForm.tsx";
import { TripSummary } from "./components/TripSummary.tsx";
import { ForecastSlider } from "./components/ForecastSlider.tsx";
import { useForecast } from "./hooks/useForecast.ts";
import { usePlan, type PlanCall } from "./hooks/usePlan.ts";
import { focusIfLost } from "./lib/focus.ts";
import { formatDuration } from "./lib/format.ts";
import { MapView } from "./map/MapView.tsx";

export function App() {
  const warmUp = useWarmUp();
  const plan = usePlan();
  const [lastCall, setLastCall] = useState<PlanCall | null>(null);
  const planned = lastCall?.request ?? null;
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(true);
  // Once a trip is planned the form folds into a summary, so that the routes fit on screen.
  const [formOpen, setFormOpen] = useState(true);
  const formId = useId();
  const formRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  const forecast = useForecast(plan.data ?? null);
  const routes = plan.data?.routes ?? [];
  // The user's pick if it is on screen, otherwise the recommended route.
  const selectedId = routes.some((route) => route.id === chosenId)
    ? chosenId
    : (plan.data?.recommended_route_id ?? routes[0]?.id ?? null);

  // Stable between slider moves, so the panel's memoized parts and the map's route layers
  // are left alone while only the hour changes.
  const selection = useMemo(() => ({ selectedId, hoveredId }), [selectedId, hoveredId]);
  const { mutate } = plan;
  const run = useCallback(
    (call: PlanCall) => {
      setLastCall(call);
      setChosenId(null);
      // On a phone, fold the sheet away to show the map when the plan arrives; open it for an error.
      mutate(call, {
        onSuccess: () => {
          setSheetOpen(false);
          setFormOpen(false);
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
          setFormOpen(true);
        },
      });
    },
    [mutate],
  );
  const planTrip = useCallback(
    (request: PlanRequest) => {
      run({ kind: "trip", request });
    },
    [run],
  );
  const planDemo = useCallback(
    (request: PlanRequest) => {
      run({ kind: "demo", request });
    },
    [run],
  );
  const editTrip = useCallback(() => {
    setFormOpen(true);
    requestAnimationFrame(() => {
      formRef.current?.querySelector<HTMLElement>("input")?.focus();
    });
  }, []);
  const retry = useCallback(() => {
    if (lastCall !== null) {
      run(lastCall);
    }
  }, [lastCall, run]);
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
          {planned !== null && !formOpen && (
            <TripSummary request={planned} formId={formId} onEdit={editTrip} />
          )}
          <div id={formId} ref={formRef} hidden={planned !== null && !formOpen}>
            <TripForm planned={planned} onSubmit={planTrip} onDemo={planDemo} />
          </div>
          <PlanStatus
            pending={plan.isPending}
            error={plan.error}
            plan={plan.data ?? null}
            onRetry={retry}
          />
          {hasNothingYet && (
            <p className="empty-state">
              Check where you start and where you are going, or change them. You will see up to
              three routes, ranked by weather risk, and a forecast for the next 48 hours along them.
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
              <RankingTable plan={plan.data} />
            </>
          )}
        </>
      }
      map={
        <MapView
          plan={plan.data ?? null}
          selection={selection}
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
