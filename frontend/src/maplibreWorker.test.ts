import type { Plugin } from "vite";
import { describe, expect, it, vi } from "vitest";

import { maplibreWorker, WORKER_FILE } from "../maplibreWorker.ts";

describe("maplibreWorker", () => {
  it("puts the worker where MapLibre looks for it: beside its script in assets", () => {
    interface Emitted {
      type: string;
      fileName: string;
      source: Uint8Array;
    }
    const emitted: Emitted[] = [];
    const plugin = maplibreWorker() as Plugin & { generateBundle: () => void };

    plugin.generateBundle.call({ emitFile: vi.fn((file: Emitted) => emitted.push(file)) });

    expect(WORKER_FILE).toBe("assets/maplibre-gl-worker.mjs");
    expect(emitted).toHaveLength(1);
    expect(emitted[0]).toMatchObject({ type: "asset", fileName: WORKER_FILE });
    expect(emitted[0]?.source.length).toBeGreaterThan(100_000); // the real worker, not a stub
  });

  it("only takes part in a production build", () => {
    expect(maplibreWorker().apply).toBe("build");
  });
});
