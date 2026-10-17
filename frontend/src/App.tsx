import { useWarmUp } from "./api/useWarmUp.ts";

export function App() {
  useWarmUp();
  return (
    <main>
      <h1>Weather-Aware Truck Routing</h1>
      <p>Pick a route, check the weather along it, and drive the safest one.</p>
    </main>
  );
}
