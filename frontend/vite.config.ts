import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    // MapLibre is a lazy chunk of about 1 MB (290 KB gzipped) outside the first-load budget.
    chunkSizeWarningLimit: 1200,
  },
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
