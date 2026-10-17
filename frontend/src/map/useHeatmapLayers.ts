import type { FeatureCollection, Point } from "geojson";
import { useEffect, useRef, useState } from "react";

import { createFrameScheduler } from "../lib/frameScheduler.ts";
import type { HeatProperties } from "./heatmapData.ts";
import { installHeatmapLayers, setHeatmapFrame } from "./heatmapLayers.ts";
import type { MapState } from "./useMap.ts";
import { whenStyleLoaded } from "./whenStyleLoaded.ts";

type Frames = readonly FeatureCollection<Point, HeatProperties>[];

/**
 * Draws one frame of the heatmap and changes it as `hour` moves. The layers are added once. A
 * new set of frames is drawn at once; a new hour is drawn on the next animation frame, and only
 * the last hour asked for in between, so a fast slider costs one redraw per frame.
 */
export function useHeatmapLayers(mapState: MapState, frames: Frames | null, hour: number): void {
  const map = mapState.map;
  const [installed, setInstalled] = useState(false);
  const drawn = useRef<Frames | null>(null);

  useEffect(() => {
    if (map === null) {
      return;
    }
    const stopWaiting = whenStyleLoaded(map, () => {
      installHeatmapLayers(map);
      setInstalled(true);
    });
    return () => {
      stopWaiting();
      drawn.current = null;
      setInstalled(false);
    };
  }, [map]);

  useEffect(() => {
    if (map === null || !installed) {
      return;
    }
    if (drawn.current !== frames) {
      // A new plan or variable: draw its frame without waiting.
      drawn.current = frames;
      setHeatmapFrame(map, frames?.[hour] ?? { type: "FeatureCollection", features: [] });
      return;
    }
    // A new hour of the same frames: one redraw per animation frame, the last hour asked for.
    const scheduler = createFrameScheduler((index) => {
      const frame = frames?.[index];
      if (frame !== undefined) {
        setHeatmapFrame(map, frame);
      }
    });
    scheduler.schedule(hour);
    return scheduler.cancel;
  }, [map, installed, frames, hour]);
}
