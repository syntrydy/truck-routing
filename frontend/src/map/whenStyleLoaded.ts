import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";

/** MapLibre types `getStyle()` as always there, but it answers `undefined` until the JSON is in. */
function styleIsLoaded(map: MapLibreMap): boolean {
  return (map.getStyle() as StyleSpecification | undefined) !== undefined;
}

/**
 * Runs `callback` once the basemap style is loaded: now if it is, otherwise as soon as it
 * arrives. `isStyleLoaded()` is also false while tiles load, and `load` may have fired already,
 * so this waits on the style itself. Returns a function that stops waiting.
 */
export function whenStyleLoaded(map: MapLibreMap, callback: () => void): () => void {
  let done = false;
  const run = () => {
    if (done || !styleIsLoaded(map)) {
      return;
    }
    done = true;
    map.off("styledata", run);
    callback();
  };
  map.on("styledata", run);
  run();
  return () => {
    done = true;
    map.off("styledata", run);
  };
}
