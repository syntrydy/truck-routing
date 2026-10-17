import type { Marker } from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { PlanResponse } from "../api/types.ts";
import { frameTime } from "../lib/forecastTime.ts";
import { buildTruckElement, truckPosition } from "./truck.ts";
import type { MapState } from "./useMap.ts";

type Route = PlanResponse["routes"][number];

/**
 * Puts a truck on the selected route where it will be at the forecast hour. The marker is
 * made once and moved; it goes when there is no route to follow.
 */
export function useTruckMarker(
  mapState: MapState,
  route: Route | undefined,
  startIso: string | undefined,
  hour: number,
): void {
  const marker = useRef<Marker | null>(null);
  const map = mapState.map;
  const maplibre = mapState.status === "ready" ? mapState.maplibre : null;

  useEffect(() => {
    const position =
      route === undefined || startIso === undefined
        ? null
        : truckPosition(route.checkpoints, frameTime(startIso, hour).getTime());
    if (map === null || maplibre === null || position === null) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    if (marker.current === null) {
      marker.current = new maplibre.Marker({ element: buildTruckElement() })
        .setLngLat(position)
        .addTo(map);
    } else {
      marker.current.setLngLat(position);
    }
  }, [map, maplibre, route, startIso, hour]);

  useEffect(
    () => () => {
      marker.current?.remove();
      marker.current = null;
    },
    [map],
  );
}
