import { useState } from "react";

import type { PlanRequest } from "./api/types.ts";
import { useWarmUp } from "./api/useWarmUp.ts";
import { AppShell } from "./components/AppShell.tsx";
import { TripForm } from "./components/TripForm.tsx";
import { MapView } from "./map/MapView.tsx";

export function App() {
  useWarmUp();
  // Until planning is wired to the API, the last submitted request stands for the plan shown.
  const [planned, setPlanned] = useState<PlanRequest | null>(null);
  return (
    <AppShell
      panel={
        <>
          <h1>Weather-Aware Truck Routing</h1>
          <p>Pick a route, check the weather along it, and drive the safest one.</p>
          <TripForm planned={planned} onSubmit={setPlanned} />
        </>
      }
      map={<MapView />}
      slider={<p>The forecast slider appears once a trip is planned.</p>}
    />
  );
}
