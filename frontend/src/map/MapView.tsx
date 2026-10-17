import { useRef } from "react";

import type { PlanResponse } from "../api/types.ts";
import type { RouteSelection } from "./routeData.ts";
import { useMap } from "./useMap.ts";
import { useRouteLayers } from "./useRouteLayers.ts";

interface MapViewProps {
  /** The plan to draw, if there is one. */
  plan: PlanResponse | null;
  selection: RouteSelection;
  onSelectRoute: (routeId: string) => void;
  onHoverRoute: (routeId: string | null) => void;
}

/** The basemap with the routes and checkpoints of the plan drawn on it. */
export function MapView({ plan, selection, onSelectRoute, onHoverRoute }: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapState = useMap(container);
  useRouteLayers(mapState, plan, selection, { onSelectRoute, onHoverRoute });

  return (
    <div className="map-view">
      <div ref={container} className="map-view__canvas" data-testid="map-canvas" />
      {mapState.status === "loading" && (
        <p className="map-view__message" role="status">
          Loading the map…
        </p>
      )}
      {mapState.status === "error" && (
        <p className="map-view__message" role="alert">
          The map could not be loaded. Check that your browser supports WebGL and that you are
          online, then reload the page.
        </p>
      )}
    </div>
  );
}
