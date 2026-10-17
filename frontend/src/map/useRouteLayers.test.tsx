import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PlanResponse } from "../api/types.ts";
import { samplePlan } from "../test/plan.ts";
import { fake, fakeMapLibreModule, type FakeMap } from "./fakeMapLibre.ts";
import { MapView } from "./MapView.tsx";
import type { RouteSelection } from "./routeData.ts";
import { CHECKPOINTS_LAYER, ROUTES_LINE_LAYER } from "./routeLayers.ts";

vi.mock("maplibre-gl", () => fakeMapLibreModule);

beforeEach(() => {
  fake.reset();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const NONE: RouteSelection = { selectedId: null, hoveredId: null };

function props(overrides: Partial<Parameters<typeof MapView>[0]> = {}) {
  return {
    plan: null as PlanResponse | null,
    selection: NONE,
    onSelectRoute: vi.fn(),
    onHoverRoute: vi.fn(),
    forecast: { frames: null, hour: 0 },
    ...overrides,
  };
}

async function mapCreated(): Promise<FakeMap> {
  await waitFor(() => {
    expect(fake.maps).toHaveLength(1);
  });
  return fake.maps[0] as FakeMap;
}

async function installed(initial = props()) {
  const view = render(<MapView {...initial} />);
  const map = await mapCreated();
  await waitFor(() => {
    expect(map.layers).toHaveLength(5);
  });
  return { ...view, map, callbacks: initial };
}

const features = (map: FakeMap, source: string) =>
  (map.sources.get(source)?.data as { features: { properties: Record<string, unknown> }[] })
    .features;

describe("adding the layers", () => {
  it("adds the routes and the checkpoints, with the checkpoints on top", async () => {
    const { map } = await installed();

    expect([...map.sources.keys()].slice(0, 2)).toEqual(["routes", "checkpoints"]);
    expect(map.layers.slice(0, 3).map(({ id, type, source }) => [id, type, source])).toEqual([
      ["routes-casing", "line", "routes"],
      ["routes-line", "line", "routes"],
      ["checkpoints", "circle", "checkpoints"],
    ]);
  });

  it("starts empty", async () => {
    const { map } = await installed();

    expect(features(map, "routes")).toEqual([]);
    expect(features(map, "checkpoints")).toEqual([]);
  });

  it("waits for the basemap style before adding anything, however late it comes", async () => {
    fake.styleLoaded = false;
    render(<MapView {...props({ plan: samplePlan() })} />);
    const map = await mapCreated();

    expect(map.layers).toHaveLength(0);

    fake.styleLoaded = true;
    map.emit("styledata");

    await waitFor(() => {
      expect(map.layers).toHaveLength(5);
    });
    await waitFor(() => {
      expect(features(map, "routes")).toHaveLength(2);
    });
  });

  it("adds them once, however often the plan and the selection change", async () => {
    const { map, rerender, callbacks } = await installed();

    rerender(
      <MapView {...callbacks} plan={samplePlan()} selection={{ ...NONE, selectedId: "r1" }} />,
    );
    rerender(
      <MapView {...callbacks} plan={samplePlan()} selection={{ ...NONE, selectedId: "r2" }} />,
    );

    expect(map.layers).toHaveLength(5);
    expect(fake.maps).toHaveLength(1);
  });
});

describe("drawing a plan", () => {
  it("draws every route and every checkpoint", async () => {
    const { map } = await installed(
      props({ plan: samplePlan(), selection: { ...NONE, selectedId: "r1" } }),
    );

    await waitFor(() => {
      expect(features(map, "routes")).toHaveLength(2);
    });
    expect(features(map, "checkpoints")).toHaveLength(5);
  });

  it("clears the map when the plan goes", async () => {
    const { map, rerender, callbacks } = await installed(props({ plan: samplePlan() }));
    await waitFor(() => {
      expect(features(map, "routes")).toHaveLength(2);
    });

    rerender(<MapView {...callbacks} plan={null} />);

    await waitFor(() => {
      expect(features(map, "routes")).toEqual([]);
    });
  });

  it("changes the data, not the layers, when the selection changes", async () => {
    const { map, rerender, callbacks } = await installed(
      props({ plan: samplePlan(), selection: { ...NONE, selectedId: "r1" } }),
    );
    const plan = callbacks.plan as PlanResponse;
    await waitFor(() => {
      expect(features(map, "routes")[0]?.properties.emphasis).toBe("selected");
    });

    rerender(<MapView {...callbacks} plan={plan} selection={{ ...NONE, selectedId: "r2" }} />);

    await waitFor(() => {
      expect(features(map, "routes")[1]?.properties.emphasis).toBe("selected");
    });
    expect(features(map, "routes")[0]?.properties.emphasis).toBe("normal");
    expect(map.layers).toHaveLength(5);
  });
});

describe("moving the view", () => {
  const BOUNDS = [
    [-105, 38],
    [-87.6, 41.9],
  ];

  it("fits the routes when a plan arrives", async () => {
    const { map } = await installed(props({ plan: samplePlan() }));

    await waitFor(() => {
      expect(map.fitBounds).toHaveBeenCalledTimes(1);
    });
    expect(map.fitBounds).toHaveBeenCalledWith(BOUNDS, {
      padding: 48,
      maxZoom: 11,
      duration: 700,
    });
  });

  it("does not move when a route is selected or hovered", async () => {
    const plan = samplePlan();
    const { map, rerender, callbacks } = await installed(props({ plan }));
    await waitFor(() => {
      expect(map.fitBounds).toHaveBeenCalledTimes(1);
    });

    rerender(
      <MapView {...callbacks} plan={plan} selection={{ selectedId: "r2", hoveredId: null }} />,
    );
    rerender(
      <MapView {...callbacks} plan={plan} selection={{ selectedId: "r2", hoveredId: "r1" }} />,
    );

    await waitFor(() => {
      expect(features(map, "routes")[0]?.properties.emphasis).toBe("hovered");
    });
    expect(map.fitBounds).toHaveBeenCalledTimes(1);
  });

  it("moves again for the next plan", async () => {
    const { map, rerender, callbacks } = await installed(props({ plan: samplePlan() }));
    await waitFor(() => {
      expect(map.fitBounds).toHaveBeenCalledTimes(1);
    });

    rerender(<MapView {...callbacks} plan={samplePlan()} />);

    await waitFor(() => {
      expect(map.fitBounds).toHaveBeenCalledTimes(2);
    });
  });

  it("does not move for an empty plan", async () => {
    const { map } = await installed(props({ plan: { ...samplePlan(), routes: [] } }));

    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(map.fitBounds).not.toHaveBeenCalled();
  });

  it("does not animate for people who ask for less motion", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { map } = await installed(props({ plan: samplePlan() }));

    await waitFor(() => {
      expect(map.fitBounds).toHaveBeenCalled();
    });
    expect(vi.mocked(map.fitBounds).mock.calls[0]?.[1]).toMatchObject({ duration: 0 });
  });
});

describe("pointing at routes", () => {
  const routeEvent = (id: string) => ({ features: [{ properties: { id } }] });

  it("reports the route under the pointer, and shows a pointer cursor", async () => {
    const { map, callbacks } = await installed();

    map.emit("mousemove", ROUTES_LINE_LAYER, routeEvent("r2"));

    expect(callbacks.onHoverRoute).toHaveBeenCalledWith("r2");
    expect(map.canvas.style.cursor).toBe("pointer");
  });

  it("reports that the pointer left", async () => {
    const { map, callbacks } = await installed();
    map.emit("mousemove", ROUTES_LINE_LAYER, routeEvent("r2"));

    map.emit("mouseleave", ROUTES_LINE_LAYER);

    expect(callbacks.onHoverRoute).toHaveBeenLastCalledWith(null);
    expect(map.canvas.style.cursor).toBe("");
  });

  it("selects the route that is clicked", async () => {
    const { map, callbacks } = await installed();

    map.emit("click", ROUTES_LINE_LAYER, routeEvent("r2"));

    expect(callbacks.onSelectRoute).toHaveBeenCalledExactlyOnceWith("r2");
  });

  it("ignores a click that carries no route", async () => {
    const { map, callbacks } = await installed();

    map.emit("click", ROUTES_LINE_LAYER, { features: [] });

    expect(callbacks.onSelectRoute).not.toHaveBeenCalled();
  });

  it("uses the latest callbacks without re-registering", async () => {
    const { map, rerender, callbacks } = await installed();
    const later = vi.fn();

    rerender(<MapView {...callbacks} onSelectRoute={later} />);
    map.emit("click", ROUTES_LINE_LAYER, routeEvent("r1"));

    expect(later).toHaveBeenCalledWith("r1");
    expect(callbacks.onSelectRoute).not.toHaveBeenCalled();
    expect(map.handlers.get(`click:${ROUTES_LINE_LAYER}`)).toHaveLength(1);
  });
});

describe("checkpoint popups", () => {
  const checkpointEvent = (routeId: string, index: number) => ({
    features: [{ properties: { routeId, index } }],
  });

  async function withPlan() {
    const context = await installed(props({ plan: samplePlan() }));
    await waitFor(() => {
      expect(features(context.map, "checkpoints")).toHaveLength(5);
    });
    return context;
  }

  it("opens at the checkpoint with its details", async () => {
    const { map } = await withPlan();

    map.emit("click", CHECKPOINTS_LAYER, checkpointEvent("r1", 2));

    const [popup] = fake.popups;
    const checkpoint = samplePlan().routes[0]?.checkpoints[2];
    expect(popup?.lngLat).toEqual([checkpoint?.lon, checkpoint?.lat]);
    expect(popup?.content?.querySelector("h3")?.textContent).toBe("Route R1, mile 50");
    expect(popup?.content?.querySelector(".popup__level")?.textContent).toBe("Risk: High");
  });

  it("shows a checkpoint of the other route too", async () => {
    const { map } = await withPlan();

    map.emit("click", CHECKPOINTS_LAYER, checkpointEvent("r2", 1));

    expect(fake.popups[0]?.content?.querySelector(".popup__level")?.textContent).toBe(
      "Risk: Unknown",
    );
  });

  it("replaces the popup that was open", async () => {
    const { map } = await withPlan();

    map.emit("click", CHECKPOINTS_LAYER, checkpointEvent("r1", 0));
    map.emit("click", CHECKPOINTS_LAYER, checkpointEvent("r1", 1));

    expect(fake.popups).toHaveLength(2);
    expect(fake.popups[0]?.remove).toHaveBeenCalledTimes(1);
    expect(fake.popups[1]?.remove).not.toHaveBeenCalled();
  });

  it("closes when a new plan arrives", async () => {
    const { map, rerender, callbacks } = await withPlan();
    map.emit("click", CHECKPOINTS_LAYER, checkpointEvent("r1", 0));

    rerender(<MapView {...callbacks} plan={samplePlan()} />);

    expect(fake.popups[0]?.remove).toHaveBeenCalled();
  });

  it("does not open for a checkpoint the plan does not have", async () => {
    const { map } = await withPlan();

    map.emit("click", CHECKPOINTS_LAYER, checkpointEvent("r9", 0));
    map.emit("click", CHECKPOINTS_LAYER, checkpointEvent("r1", 99));
    map.emit("click", CHECKPOINTS_LAYER, { features: [] });

    expect(fake.popups).toHaveLength(0);
  });

  it("shows a pointer cursor over a checkpoint", async () => {
    const { map } = await withPlan();

    map.emit("mouseenter", CHECKPOINTS_LAYER);
    expect(map.canvas.style.cursor).toBe("pointer");
    map.emit("mouseleave", CHECKPOINTS_LAYER);
    expect(map.canvas.style.cursor).toBe("");
  });
});

describe("leaving", () => {
  it("stops listening and closes the popup when the map goes away", async () => {
    const { map, unmount } = await installed(props({ plan: samplePlan() }));
    await waitFor(() => {
      expect(features(map, "checkpoints")).toHaveLength(5);
    });
    map.emit("click", CHECKPOINTS_LAYER, {
      features: [{ properties: { routeId: "r1", index: 0 } }],
    });

    unmount();

    for (const handlers of map.handlers.values()) {
      expect(handlers).toEqual([]);
    }
    expect(fake.popups[0]?.remove).toHaveBeenCalled();
  });
});
