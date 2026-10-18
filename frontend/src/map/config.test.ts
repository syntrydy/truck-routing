import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("the basemap style", () => {
  it("is the light one: no shaded-relief images to wait for", async () => {
    vi.stubEnv("VITE_MAP_STYLE_URL", undefined);
    vi.resetModules();

    const { MAP_STYLE_URL } = await import("./config.ts");

    expect(MAP_STYLE_URL).toBe("https://tiles.openfreemap.org/styles/bright");
  });

  it("can be replaced from the environment", async () => {
    vi.stubEnv("VITE_MAP_STYLE_URL", "https://tiles.example/style.json");
    vi.resetModules();

    const { MAP_STYLE_URL } = await import("./config.ts");

    expect(MAP_STYLE_URL).toBe("https://tiles.example/style.json");
  });
});
