import { useWarmUp } from "./api/useWarmUp.ts";
import { AppShell } from "./components/AppShell.tsx";
import { MapView } from "./map/MapView.tsx";

export function App() {
  useWarmUp();
  return (
    <AppShell
      panel={
        <>
          <h1>Weather-Aware Truck Routing</h1>
          <p>Pick a route, check the weather along it, and drive the safest one.</p>
        </>
      }
      map={<MapView />}
      slider={<p>The forecast slider appears once a trip is planned.</p>}
    />
  );
}
