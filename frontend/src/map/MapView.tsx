import { useRef } from "react";

import { useMap } from "./useMap.ts";

/** The basemap. Everything drawn on it is added through `useMap`'s map by other hooks. */
export function MapView() {
  const container = useRef<HTMLDivElement>(null);
  const { status } = useMap(container);

  return (
    <div className="map-view">
      <div ref={container} className="map-view__canvas" data-testid="map-canvas" />
      {status === "loading" && (
        <p className="map-view__message" role="status">
          Loading the map…
        </p>
      )}
      {status === "error" && (
        <p className="map-view__message" role="alert">
          The map could not be loaded. Check that your browser supports WebGL and that you are
          online, then reload the page.
        </p>
      )}
    </div>
  );
}
