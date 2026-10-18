import { act, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { sampleHeatmap, samplePlan } from "../test/plan.ts";
import { fake, fakeMapLibreModule, type FakeMap } from "./fakeMapLibre.ts";
import { buildHeatmapFrames } from "./heatmapData.ts";
import { MapView } from "./MapView.tsx";

vi.mock("maplibre-gl", () => fakeMapLibreModule);

/** Animation frames that run only when the test says the browser has drawn one. */
const frames = {
  queue: [] as (() => void)[],
  tick() {
    const waiting = this.queue.splice(0);
    act(() => {
      waiting.forEach((callback) => {
        callback();
      });
    });
  },
};

beforeEach(() => {
  fake.reset();
  frames.queue = [];
  vi.stubGlobal("requestAnimationFrame", (callback: () => void) => frames.queue.push(callback));
  vi.stubGlobal("cancelAnimationFrame", (handle: number) => {
    frames.queue[handle - 1] = () => undefined;
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const risk = buildHeatmapFrames(sampleHeatmap(), "risk");
const wind = buildHeatmapFrames(sampleHeatmap(), "wind");

function props(overrides: Partial<Parameters<typeof MapView>[0]> = {}) {
  return {
    plan: samplePlan(),
    selection: { selectedId: "r1", hoveredId: null },
    onSelectRoute: vi.fn(),
    onHoverRoute: vi.fn(),
    forecast: { frames: risk, hour: 0 },
    ...overrides,
  };
}

async function installed(initial = props()) {
  const view = render(<MapView {...initial} />);
  await waitFor(() => {
    expect(fake.maps).toHaveLength(1);
  });
  const map = fake.maps[0] as FakeMap;
  await waitFor(() => {
    expect(map.sources.has("heatmap")).toBe(true);
  });
  return { ...view, map, initial };
}

const drawn = (map: FakeMap) => map.sources.get("heatmap");
const shownValues = (map: FakeMap) =>
  (drawn(map)?.data as { features: { properties: { value: number } }[] }).features.map(
    (feature) => feature.properties.value,
  );

describe("the layers", () => {
  it("are two circle layers, a soft one and a crisp one, under the basemap's place names", async () => {
    const { map } = await installed();

    const layers = map.layers.filter((layer) => layer.source === "heatmap");
    expect(layers.map(({ id, type }) => [id, type])).toEqual([
      ["heatmap-glow", "circle"],
      ["heatmap-points", "circle"],
    ]);
    expect(layers.every((layer) => layer.before === "place-labels")).toBe(true);
  });

  it("are added once, however many frames are drawn", async () => {
    const { map, rerender, initial } = await installed();

    rerender(<MapView {...initial} forecast={{ frames: wind, hour: 5 }} />);
    rerender(<MapView {...initial} forecast={{ frames: wind, hour: 6 }} />);

    expect(map.layers.filter((layer) => layer.source === "heatmap")).toHaveLength(2);
  });
});

describe("drawing frames", () => {
  it("draws the frame of the hour as soon as there are frames", async () => {
    const { map } = await installed(props({ forecast: { frames: risk, hour: 4 } }));

    await waitFor(() => {
      expect(shownValues(map)).toEqual([0, 1, 0.5]);
    });
  });

  it("draws a new hour on the next animation frame, not at once", async () => {
    const { map, rerender, initial } = await installed();
    await waitFor(() => {
      expect(drawn(map)?.setData).toHaveBeenCalled();
    });
    const callsBefore = vi.mocked(drawn(map)?.setData ?? vi.fn()).mock.calls.length;

    rerender(<MapView {...initial} forecast={{ frames: risk, hour: 3 }} />);
    expect(drawn(map)?.setData).toHaveBeenCalledTimes(callsBefore);
    frames.tick();

    expect(drawn(map)?.setData).toHaveBeenCalledTimes(callsBefore + 1);
    expect(shownValues(map)).toEqual([0, 0.75, 0.5]);
  });

  it("redraws at most once per animation frame, with the last hour asked for", async () => {
    const { map, rerender, initial } = await installed();
    await waitFor(() => {
      expect(drawn(map)?.setData).toHaveBeenCalled();
    });
    const callsBefore = vi.mocked(drawn(map)?.setData ?? vi.fn()).mock.calls.length;

    for (const hour of [1, 2, 3, 4, 5, 6, 7, 8]) {
      rerender(<MapView {...initial} forecast={{ frames: risk, hour }} />);
    }
    frames.tick();

    expect(drawn(map)?.setData).toHaveBeenCalledTimes(callsBefore + 1);
    expect(shownValues(map)).toEqual(risk[8]?.features.map((feature) => feature.properties.value));
  });

  it("draws nothing for hours that were dropped by a later change", async () => {
    const { map, rerender, initial } = await installed();
    await waitFor(() => {
      expect(drawn(map)?.setData).toHaveBeenCalled();
    });

    rerender(<MapView {...initial} forecast={{ frames: risk, hour: 2 }} />);
    rerender(<MapView {...initial} forecast={{ frames: risk, hour: 3 }} />);
    frames.tick();
    frames.tick();

    const last = vi.mocked(drawn(map)?.setData ?? vi.fn()).mock.calls.at(-1)?.[0] as {
      features: { properties: { value: number } }[];
    };
    expect(last.features.map((feature) => feature.properties.value)).toEqual([0, 0.75, 0.5]);
  });

  it("draws another variable's frame at once", async () => {
    const { map, rerender, initial } = await installed(
      props({ forecast: { frames: risk, hour: 2 } }),
    );
    await waitFor(() => {
      expect(shownValues(map)).toEqual([0, 0.5, 0.5]);
    });

    rerender(<MapView {...initial} forecast={{ frames: wind, hour: 2 }} />);

    expect(shownValues(map)).toEqual(wind[2]?.features.map((feature) => feature.properties.value));
  });

  it("empties the layer when the plan is gone", async () => {
    const { map, rerender, initial } = await installed();
    await waitFor(() => {
      expect(shownValues(map)).toHaveLength(3);
    });

    rerender(<MapView {...initial} plan={null} forecast={{ frames: null, hour: 0 }} />);

    expect(shownValues(map)).toEqual([]);
  });

  it("marks unknown places as unknown for the layers to colour grey", async () => {
    const { map } = await installed(props({ forecast: { frames: risk, hour: 0 } }));

    await waitFor(() => {
      expect(drawn(map)?.setData).toHaveBeenCalled();
    });
    const features = (drawn(map)?.data as { features: { properties: { known: boolean } }[] })
      .features;
    expect(features.map((feature) => feature.properties.known)).toEqual([true, true, false]);
  });

  it("waits for the basemap style like the route layers do", async () => {
    fake.styleLoaded = false;
    render(<MapView {...props()} />);
    await waitFor(() => {
      expect(fake.maps).toHaveLength(1);
    });
    const map = fake.maps[0] as FakeMap;
    expect(map.sources.has("heatmap")).toBe(false);

    fake.styleLoaded = true;
    act(() => {
      map.emit("styledata");
    });

    await waitFor(() => {
      expect(map.sources.has("heatmap")).toBe(true);
    });
  });
});

describe("the truck", () => {
  const checkpoints = samplePlan().routes[0]?.checkpoints ?? [];

  it("is on the selected route, at the start while the hour is the departure", async () => {
    await installed();

    await waitFor(() => {
      expect(fake.markers).toHaveLength(1);
    });
    const first = checkpoints[0];
    expect(fake.markers[0]?.lngLat).toEqual([first?.lon, first?.lat]);
    expect(fake.markers[0]?.added).toBe(true);
    expect(fake.markers[0]?.options.element).toHaveAttribute("role", "img");
  });

  it("moves along the route with the hour, as one marker", async () => {
    const { rerender, initial } = await installed();
    await waitFor(() => {
      expect(fake.markers).toHaveLength(1);
    });
    const start = fake.markers[0]?.lngLat;

    // Every checkpoint of the sample shares the ETA 19:00 UTC, the first frame, so use a
    // route whose checkpoints are an hour apart.
    const plan = samplePlan();
    plan.routes[0]?.checkpoints.forEach((checkpoint, index) => {
      checkpoint.eta = `2026-10-18T${String(19 + index * 2)}:00:00Z`;
    });
    rerender(<MapView {...initial} plan={plan} forecast={{ frames: risk, hour: 1 }} />);

    await waitFor(() => {
      expect(fake.markers[0]?.lngLat).not.toEqual(start);
    });
    expect(fake.markers).toHaveLength(1);
    const [a, b] = plan.routes[0]?.checkpoints ?? [];
    expect(fake.markers[0]?.lngLat).toEqual([
      ((a?.lon ?? 0) + (b?.lon ?? 0)) / 2,
      ((a?.lat ?? 0) + (b?.lat ?? 0)) / 2,
    ]);
  });

  it("follows the route that is selected", async () => {
    const { rerender, initial } = await installed();
    await waitFor(() => {
      expect(fake.markers).toHaveLength(1);
    });

    rerender(<MapView {...initial} selection={{ selectedId: "r2", hoveredId: null }} />);

    const second = samplePlan().routes[1]?.checkpoints[0];
    await waitFor(() => {
      expect(fake.markers[0]?.lngLat).toEqual([second?.lon, second?.lat]);
    });
  });

  it("goes when there is no plan, and when the map goes", async () => {
    const { rerender, initial, unmount } = await installed();
    await waitFor(() => {
      expect(fake.markers).toHaveLength(1);
    });

    rerender(<MapView {...initial} plan={null} forecast={{ frames: null, hour: 0 }} />);
    await waitFor(() => {
      expect(fake.markers[0]?.remove).toHaveBeenCalled();
    });

    rerender(<MapView {...initial} />);
    await waitFor(() => {
      expect(fake.markers).toHaveLength(2);
    });
    unmount();
    expect(fake.markers[1]?.remove).toHaveBeenCalled();
  });
});
