import type { MapLayerMouseEvent, Popup } from "maplibre-gl";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import type { PlanResponse } from "../api/types.ts";
import { buildCheckpointPopup } from "./popup.ts";
import type { RouteSelection } from "./routeData.ts";
import {
  CHECKPOINTS_LAYER,
  fitToRoutes,
  installRouteLayers,
  ROUTES_LINE_LAYER,
  setRouteData,
} from "./routeLayers.ts";
import type { MapState } from "./useMap.ts";
import { whenStyleLoaded } from "./whenStyleLoaded.ts";

interface RouteLayerCallbacks {
  onSelectRoute: (routeId: string) => void;
  onHoverRoute: (routeId: string | null) => void;
}

function stringProperty(event: MapLayerMouseEvent, name: string): string | null {
  const value: unknown = event.features?.[0]?.properties[name];
  return typeof value === "string" ? value : null;
}

/**
 * Draws the routes and checkpoints of `plan` on the map and reports what the user points at.
 * The layers are added once; after that only their data changes, and the view moves only when
 * a new plan arrives, not when a route is selected.
 */
export function useRouteLayers(
  mapState: MapState,
  plan: PlanResponse | null,
  selection: RouteSelection,
  { onSelectRoute, onHoverRoute }: RouteLayerCallbacks,
): void {
  const [installed, setInstalled] = useState(false);
  const popup = useRef<Popup | null>(null);
  const routes = plan?.routes;
  const map = mapState.map;
  const maplibre = mapState.status === "ready" ? mapState.maplibre : null;

  const selectRoute = useEffectEvent(onSelectRoute);
  const hoverRoute = useEffectEvent(onHoverRoute);
  const showCheckpoint = useEffectEvent((event: MapLayerMouseEvent) => {
    const routeId = stringProperty(event, "routeId");
    const index: unknown = event.features?.[0]?.properties.index;
    const route = routes?.find((candidate) => candidate.id === routeId);
    const checkpoint = route?.checkpoints.find((candidate) => candidate.index === index);
    if (maplibre === null || map === null || route === undefined || checkpoint === undefined) {
      return;
    }
    popup.current?.remove();
    popup.current = new maplibre.Popup({ maxWidth: "20rem" })
      .setLngLat([checkpoint.lon, checkpoint.lat])
      .setDOMContent(buildCheckpointPopup(checkpoint, route.label))
      .addTo(map);
  });

  useEffect(() => {
    if (map === null) {
      return;
    }
    const setCursor = (cursor: string) => {
      map.getCanvas().style.cursor = cursor;
    };
    const onRouteMove = (event: MapLayerMouseEvent) => {
      setCursor("pointer");
      hoverRoute(stringProperty(event, "id"));
    };
    const onRouteLeave = () => {
      setCursor("");
      hoverRoute(null);
    };
    const onRouteClick = (event: MapLayerMouseEvent) => {
      const id = stringProperty(event, "id");
      if (id !== null) {
        selectRoute(id);
      }
    };
    const onCheckpointClick = (event: MapLayerMouseEvent) => {
      showCheckpoint(event);
    };
    const onCheckpointEnter = () => {
      setCursor("pointer");
    };
    const onCheckpointLeave = () => {
      setCursor("");
    };

    const stopWaiting = whenStyleLoaded(map, () => {
      installRouteLayers(map);
      map.on("mousemove", ROUTES_LINE_LAYER, onRouteMove);
      map.on("mouseleave", ROUTES_LINE_LAYER, onRouteLeave);
      map.on("click", ROUTES_LINE_LAYER, onRouteClick);
      map.on("click", CHECKPOINTS_LAYER, onCheckpointClick);
      map.on("mouseenter", CHECKPOINTS_LAYER, onCheckpointEnter);
      map.on("mouseleave", CHECKPOINTS_LAYER, onCheckpointLeave);
      setInstalled(true);
    });

    return () => {
      stopWaiting();
      map.off("mousemove", ROUTES_LINE_LAYER, onRouteMove);
      map.off("mouseleave", ROUTES_LINE_LAYER, onRouteLeave);
      map.off("click", ROUTES_LINE_LAYER, onRouteClick);
      map.off("click", CHECKPOINTS_LAYER, onCheckpointClick);
      map.off("mouseenter", CHECKPOINTS_LAYER, onCheckpointEnter);
      map.off("mouseleave", CHECKPOINTS_LAYER, onCheckpointLeave);
      setInstalled(false);
    };
  }, [map]);

  // A popup belongs to the plan it was opened on.
  useEffect(() => {
    return () => {
      popup.current?.remove();
      popup.current = null;
    };
  }, [routes, map]);

  useEffect(() => {
    if (map !== null && installed) {
      setRouteData(map, routes ?? [], selection);
    }
  }, [map, installed, routes, selection]);

  useEffect(() => {
    if (map !== null && installed && routes !== undefined) {
      fitToRoutes(map, routes);
    }
  }, [map, installed, routes]);
}
