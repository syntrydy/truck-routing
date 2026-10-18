import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

import { maplibreWorker } from "./maplibreWorker.ts";

export default defineConfig({
  plugins: [react(), maplibreWorker()],
  build: {
    // MapLibre is a lazy chunk of about 1 MB (290 KB gzipped) outside the first-load budget.
    chunkSizeWarningLimit: 1200,
  },
  // MapLibre starts its worker from a file next to itself; pre-bundling would move it away.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: { proxy: { "/api": "http://localhost:8000" } },
  preview: { proxy: { "/api": "http://localhost:8000" } },
  test: {
    environment: "jsdom",
    // Times in tests are read in one fixed zone, so that results do not depend on the machine.
    env: { TZ: "America/Chicago" },
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // The browser tests run under Playwright, not here.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
