import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useState, type RefObject } from "react";

import { ATTRIBUTION, INITIAL_CENTER, INITIAL_ZOOM, MAP_STYLE_URL } from "./config.ts";

type MapLibre = typeof import("maplibre-gl");

export type MapState =
  | { status: "loading"; map: null }
  /** `maplibre` is the library itself, for the classes other hooks need (popups, markers). */
  | { status: "ready"; map: MapLibreMap; maplibre: MapLibre }
  | { status: "error"; map: null; error: Error };

const LOADING: MapState = { status: "loading", map: null };

let loading: Promise<MapLibre> | undefined;

/**
 * MapLibre and its stylesheet, fetched on first use so they stay out of the first bundle.
 * Every caller shares one load; a failed load is forgotten, so the next caller tries again.
 */
function loadMapLibre() {
  loading ??= Promise.all([import("maplibre-gl"), import("maplibre-gl/dist/maplibre-gl.css")])
    .then(([maplibre]) => maplibre)
    .catch((cause: unknown) => {
      loading = undefined;
      throw cause;
    });
  return loading;
}

/**
 * Creates the map inside `container` once, and removes it when the component goes away.
 * The map never depends on props or state, so re-rendering cannot re-create it; layers are
 * added by other hooks through the returned `map`.
 */
export function useMap(container: RefObject<HTMLElement | null>): MapState {
  const [state, setState] = useState<MapState>(LOADING);

  useEffect(() => {
    const element = container.current;
    if (element === null) {
      return;
    }
    let cancelled = false;
    let created: MapLibreMap | null = null;

    loadMapLibre()
      .then((maplibre) => {
        if (cancelled) {
          return;
        }
        created = new maplibre.Map({
          container: element,
          style: MAP_STYLE_URL,
          center: INITIAL_CENTER,
          zoom: INITIAL_ZOOM,
          attributionControl: false,
        });
        if (import.meta.env.DEV) {
          // The end-to-end test finds checkpoints on screen through the map; never in a build.
          Object.assign(window, { __truckMap: created });
        }
        created.addControl(
          new maplibre.AttributionControl({ compact: false, customAttribution: [...ATTRIBUTION] }),
        );
        created.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
        setState({ status: "ready", map: created, maplibre });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          const error = cause instanceof Error ? cause : new Error("The map could not start");
          setState({ status: "error", map: null, error });
        }
      });

    return () => {
      cancelled = true;
      created?.remove();
      setState(LOADING);
    };
  }, [container]);

  return state;
}
