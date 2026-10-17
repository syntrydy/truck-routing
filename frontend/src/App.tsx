import { useState } from "react";

import type { PlanRequest } from "./api/types.ts";
import { useWarmUp } from "./api/useWarmUp.ts";
import { AppShell } from "./components/AppShell.tsx";
import { PlanBanners } from "./components/PlanBanners.tsx";
import { PlanStatus } from "./components/PlanStatus.tsx";
import { RouteCards } from "./components/RouteCards.tsx";
import { TripForm } from "./components/TripForm.tsx";
import { ForecastSlider } from "./components/ForecastSlider.tsx";
import { useForecast } from "./hooks/useForecast.ts";
import { usePlan } from "./hooks/usePlan.ts";
import { MapView } from "./map/MapView.tsx";

export function App() {
  useWarmUp();
  const plan = usePlan();
  const [planned, setPlanned] = useState<PlanRequest | null>(null);
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const forecast = useForecast(plan.data ?? null);
  const routes = plan.data?.routes ?? [];
  // The user's pick if it is on screen, otherwise the recommended route.
  const selectedId = routes.some((route) => route.id === chosenId)
    ? chosenId
    : (plan.data?.recommended_route_id ?? routes[0]?.id ?? null);

  return (
    <AppShell
      panel={
        <>
          <h1>Weather-Aware Truck Routing</h1>
          <p>Pick a route, check the weather along it, and drive the safest one.</p>
          <TripForm
            planned={planned}
            onSubmit={(request) => {
              setPlanned(request);
              setChosenId(null);
              plan.mutate(request);
            }}
          />
          <PlanStatus pending={plan.isPending} error={plan.error} />
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
