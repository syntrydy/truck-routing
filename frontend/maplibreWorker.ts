import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { Plugin } from "vite";

/** Where MapLibre looks for its worker: next to its own script, which Vite puts in `assets/`. */
export const WORKER_FILE = "assets/maplibre-gl-worker.mjs";

/**
 * MapLibre starts its web worker from a file beside its own script. In a production build the
 * script is bundled into `assets/` and the worker file is left behind, so every map would run
 * without its worker: no vector tiles and no GeoJSON layers. This plugin puts the file where
 * MapLibre will look for it.
 */
export function maplibreWorker(): Plugin {
  return {
    name: "maplibre-worker",
    apply: "build",
    generateBundle() {
      const worker = new URL("./maplibre-gl-worker.mjs", import.meta.resolve("maplibre-gl"));
      this.emitFile({
        type: "asset",
        fileName: WORKER_FILE,
        source: readFileSync(fileURLToPath(worker)),
      });
    },
  };
}
