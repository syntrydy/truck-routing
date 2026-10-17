import { useRef } from "react";

import type { FeatureCollection, Point } from "geojson";

import type { PlanResponse } from "../api/types.ts";
import type { HeatProperties } from "./heatmapData.ts";
import type { RouteSelection } from "./routeData.ts";
import { useMap } from "./useMap.ts";
import { useHeatmapLayers } from "./useHeatmapLayers.ts";
import { useRouteLayers } from "./useRouteLayers.ts";
import { useTruckMarker } from "./useTruckMarker.ts";

interface MapViewProps {
  /** The plan to draw, if there is one. */
  plan: PlanResponse | null;
  selection: RouteSelection;
  onSelectRoute: (routeId: string) => void;
  onHoverRoute: (routeId: string | null) => void;
  /** The heatmap frame to show, and the hour the truck is at. */
  forecast: {
    frames: readonly FeatureCollection<Point, HeatProperties>[] | null;
    hour: number;
  };
}

/** The basemap with the routes and checkpoints of the plan drawn on it. */
export function MapView({ plan, selection, onSelectRoute, onHoverRoute, forecast }: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapState = useMap(container);
  // The routes go in first, so the heatmap layers can be placed under them.
  useRouteLayers(mapState, plan, selection, { onSelectRoute, onHoverRoute });
  useHeatmapLayers(mapState, forecast.frames, forecast.hour);
  useTruckMarker(
    mapState,
    plan?.routes.find((route) => route.id === selection.selectedId),
    plan?.heatmap.start,
    forecast.hour,
  );

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
