import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api/errors.ts";
import { apiWrapper, stubClient } from "./api/testing.tsx";
import type { ApiClient } from "./api/client.ts";
import { App } from "./App.tsx";
import { fake, fakeMapLibreModule } from "./map/fakeMapLibre.ts";
import { samplePlan } from "./test/plan.ts";
import { validateTrip } from "./lib/trip.ts";
import { CHICAGO, DENVER } from "./test/places.ts";

vi.mock("maplibre-gl", () => fakeMapLibreModule);
// The form validates on every render, so the calls count its renders.
vi.mock("./lib/trip.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./lib/trip.ts")>();
  return { ...actual, validateTrip: vi.fn(actual.validateTrip) };
});

beforeEach(() => {
  fake.reset();
});

function renderApp(overrides: Partial<ApiClient> = {}) {
  const health = vi.fn(() => Promise.resolve({ status: "ok" }));
  const geocode = vi.fn<ApiClient["geocode"]>((query) =>
    Promise.resolve({ results: query.startsWith("chi") ? [CHICAGO] : [DENVER] }),
  );
  render(<App />, { wrapper: apiWrapper(stubClient({ health, geocode, ...overrides })) });
  return { health, geocode, user: userEvent.setup() };
}

describe("App", () => {
  it("renders the application title", () => {
    renderApp();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Weather-Aware Truck Routing",
    );
  });

  it("warms the server up on load", async () => {
    const { health } = renderApp();

    await waitFor(() => {
      expect(health).toHaveBeenCalledTimes(1);
    });
  });

  it("puts the form beside the map", async () => {
    renderApp();

    await waitFor(() => {
      expect(fake.maps).toHaveLength(1);
    });
    expect(screen.getByRole("main")).toContainElement(screen.getByTestId("map-canvas"));
    expect(
      within(screen.getByRole("complementary", { name: "Trip planner" })).getByRole("combobox", {
        name: "From",
      }),
    ).toBeInTheDocument();
  });

  it("plans the trip and draws it on the map", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan()));
    const { user } = renderApp({ plan });
    await waitFor(() => {
      expect(fake.maps[0]?.layers).toHaveLength(8);
    });
    const map = fake.maps[0];

    await user.click(screen.getByRole("button", { name: "Plan trip" }));

    await waitFor(() => {
      expect(plan).toHaveBeenCalledTimes(1);
    });
    expect(plan.mock.calls[0]?.[0]).toMatchObject({
      origin: { label: CHICAGO.label },
      destination: { label: DENVER.label },
      load_lb: 42_000,
      interval_mi: 25,
    });
    await waitFor(() => {
      expect((map?.sources.get("routes")?.data as { features: unknown[] }).features).toHaveLength(
        2,
      );
    });
    expect(map?.fitBounds).toHaveBeenCalledTimes(1);
  });

  it("lists the routes and lets a card choose the route drawn as selected", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan()));
    const { user } = renderApp({ plan });
    await waitFor(() => {
      expect(fake.maps[0]?.layers).toHaveLength(8);
    });
    const map = fake.maps[0];
    await user.click(screen.getByRole("button", { name: "Plan trip" }));

    const first = await screen.findByRole("button", { name: "Route R1" });
    expect(first).toHaveAttribute("aria-pressed", "true"); // the recommended route to begin with
    const emphasis = () =>
      (
        map?.sources.get("routes")?.data as {
          features: { properties: { id: string; emphasis: string } }[];
        }
      ).features.map((feature) => `${feature.properties.id}:${feature.properties.emphasis}`);
    await waitFor(() => {
      expect(emphasis()).toEqual(["r1:selected", "r2:normal"]);
    });

    await user.click(screen.getByRole("button", { name: "Route R2" }));

    expect(screen.getByRole("button", { name: "Route R2" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await waitFor(() => {
      expect(emphasis()).toEqual(["r1:normal", "r2:selected"]);
    });
  });

  it("highlights the card of the route the pointer is over on the map", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan()));
    const { user } = renderApp({ plan });
    await waitFor(() => {
      expect(fake.maps[0]?.layers).toHaveLength(8);
    });
    await user.click(screen.getByRole("button", { name: "Plan trip" }));
    await screen.findByRole("button", { name: "Route R2" });

    act(() => {
      fake.maps[0]?.emit("mousemove", "routes-line", { features: [{ properties: { id: "r2" } }] });
    });

    expect(screen.getByRole("button", { name: "Route R2" }).closest("li")).toHaveClass(
      "route-card--hovered",
    );
  });

  async function planTrip(plan: ApiClient["plan"]) {
    const context = renderApp({ plan });
    await waitFor(() => {
      expect(fake.maps[0]?.layers).toHaveLength(8);
    });
    await context.user.click(screen.getByRole("button", { name: "Plan trip" }));
    await screen.findByRole("slider", { name: "Forecast hour" });
    return context;
  }

  const heatmapValues = () =>
    (
      fake.maps[0]?.sources.get("heatmap")?.data as {
        features: { properties: { value: number } }[];
      }
    ).features.map((feature) => feature.properties.value);

  it("offers the forecast slider only once a trip is planned", () => {
    renderApp();

    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.getByText(/forecast slider appears once a trip is planned/)).toBeInTheDocument();
  });

  it("moves the heatmap with the slider, one redraw per animation frame", async () => {
    const callbacks: (() => void)[] = [];
    vi.stubGlobal("requestAnimationFrame", (callback: () => void) => callbacks.push(callback));
    vi.stubGlobal("cancelAnimationFrame", (handle: number) => {
      callbacks[handle - 1] = () => undefined;
    });
    await planTrip(vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan())));
    await waitFor(() => {
      expect(heatmapValues()).toEqual([0, 0, 0]);
    });
    const setData = vi.mocked(fake.maps[0]?.sources.get("heatmap")?.setData ?? vi.fn());
    const before = setData.mock.calls.length;

    for (const hour of ["2", "3", "4"]) {
      fireEvent.change(screen.getByRole("slider", { name: "Forecast hour" }), {
        target: { value: hour },
      });
    }
    expect(setData).toHaveBeenCalledTimes(before);
    act(() => {
      callbacks.splice(0).forEach((callback) => {
        callback();
      });
    });

    expect(setData).toHaveBeenCalledTimes(before + 1);
    expect(heatmapValues()).toEqual([0, 1, 0.5]);
    vi.unstubAllGlobals();
  });

  it("leaves the routes alone when only the hour changes", async () => {
    await planTrip(vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan())));
    await waitFor(() => {
      expect(heatmapValues()).toEqual([0, 0, 0]);
    });
    const sources = ["routes", "checkpoints"].map((id) =>
      vi.mocked(fake.maps[0]?.sources.get(id)?.setData ?? vi.fn()),
    );
    const before = sources.map((setData) => setData.mock.calls.length);

    for (const hour of ["2", "3", "4"]) {
      fireEvent.change(screen.getByRole("slider", { name: "Forecast hour" }), {
        target: { value: hour },
      });
    }

    expect(sources.map((setData) => setData.mock.calls.length)).toEqual(before);
  });

  it("does not redraw the trip form when only the hour changes", async () => {
    await planTrip(vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan())));
    const before = vi.mocked(validateTrip).mock.calls.length;

    for (const hour of ["2", "3", "4"]) {
      fireEvent.change(screen.getByRole("slider", { name: "Forecast hour" }), {
        target: { value: hour },
      });
    }

    expect(vi.mocked(validateTrip)).toHaveBeenCalledTimes(before);
  });

  it("maps another variable when it is chosen", async () => {
    const { user } = await planTrip(vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan())));
    await waitFor(() => {
      expect(heatmapValues()).toHaveLength(3);
    });
    const risk = heatmapValues();

    await user.click(screen.getByRole("radio", { name: "Wind" }));

    await waitFor(() => {
      expect(heatmapValues()).not.toEqual(risk);
    });
    expect(screen.getByText("Severe: 45 to 55 mph")).toBeInTheDocument();
  });

  it("puts a truck on the map and says the time of the hour shown", async () => {
    await planTrip(vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan())));

    await waitFor(() => {
      expect(fake.markers).toHaveLength(1);
    });
    expect(screen.getByRole("slider", { name: "Forecast hour" })).toHaveAttribute(
      "aria-valuetext",
      "Sun, 2:00 PM CDT (UTC-05:00), at departure",
    );
  });

  it("shows why a trip could not be planned", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() =>
      Promise.reject(new ApiError({ code: "NO_ROUTE", message: "No drivable route", status: 422 })),
    );
    const { user } = renderApp({ plan });

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Plan trip" }));
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No drivable route");
  });
});

describe("states", () => {
  it("explains what to do before a first plan, and stops once there is one", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan()));
    const { user } = renderApp({ plan });
    expect(screen.getByText(/Check where you start and where you are going/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Plan trip" }));
    await screen.findByRole("button", { name: "Route R1" });

    expect(screen.queryByText(/Choose where you start/)).not.toBeInTheDocument();
  });

  it("shows progress while the plan is worked out", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() => new Promise(() => undefined));
    const { user } = renderApp({ plan });

    await user.click(screen.getByRole("button", { name: "Plan trip" }));

    expect(await screen.findByText("Planning your trip…")).toBeInTheDocument();
    expect(screen.queryByText(/Choose where you start/)).not.toBeInTheDocument();
  });

  it("offers to try again after a failure, and plans the same trip again", async () => {
    const plan = vi
      .fn<ApiClient["plan"]>()
      .mockRejectedValueOnce(
        new ApiError({
          code: "UPSTREAM_UNAVAILABLE",
          message: "down",
          status: 503,
          requestId: "req-5",
        }),
      )
      .mockResolvedValue(samplePlan());
    const { user } = renderApp({ plan });
    await user.click(screen.getByRole("button", { name: "Plan trip" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("not available right now");
    expect(alert).toHaveTextContent("Reference: req-5");
    await user.click(within(alert).getByRole("button", { name: "Try again" }));

    await screen.findByRole("button", { name: "Route R1" });
    expect(plan).toHaveBeenCalledTimes(2);
    expect(plan.mock.calls[1]?.[0]).toEqual(plan.mock.calls[0]?.[0]);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("plans the stormy demo through the demo call and says it is a recording", async () => {
    const recording = samplePlan();
    const demo = vi.fn<ApiClient["demo"]>(() =>
      Promise.resolve({ ...recording, meta: { ...recording.meta, weather_source: "demo" } }),
    );
    const plan = vi.fn<ApiClient["plan"]>();
    const { user } = renderApp({ demo, plan });

    await user.click(screen.getByRole("button", { name: "Try the stormy demo" }));

    expect(await screen.findByText(/Demo: a recording, not a live forecast/)).toBeInTheDocument();
    expect(demo).toHaveBeenCalledTimes(1);
    expect(demo.mock.calls[0]?.[0]).toMatchObject({ load_lb: 42_000, interval_mi: 25 });
    expect(plan).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "To" })).toHaveValue(
      "Salt Lake City, Utah, United States",
    );
  });

  it("tries the demo again, not a live plan, after the demo failed", async () => {
    const demo = vi
      .fn<ApiClient["demo"]>()
      .mockRejectedValueOnce(new ApiError({ code: "NETWORK", message: "down", status: 0 }))
      .mockResolvedValue(samplePlan());
    const plan = vi.fn<ApiClient["plan"]>();
    const { user } = renderApp({ demo, plan });
    await user.click(screen.getByRole("button", { name: "Try the stormy demo" }));

    await user.click(
      within(await screen.findByRole("alert")).getByRole("button", { name: "Try again" }),
    );

    await screen.findByRole("button", { name: "Route R1" });
    expect(demo).toHaveBeenCalledTimes(2);
    expect(plan).not.toHaveBeenCalled();
  });

  it("puts focus on the results when a plan arrives, and announces it", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan()));
    const { user } = renderApp({ plan });

    await user.click(screen.getByRole("button", { name: "Plan trip" }));

    const heading = await screen.findByRole("heading", { name: "Routes" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(screen.getByText(/Planned 2 routes\. Route R1 is recommended\./)).toBeInTheDocument();
  });

  it("folds the sheet away when a plan arrives, with the best route on its bar", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() => Promise.resolve(samplePlan()));
    const { user } = renderApp({ plan });
    expect(screen.getByRole("button", { name: /Trip details/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    await user.click(screen.getByRole("button", { name: "Plan trip" }));

    const bar = await screen.findByRole("button", { name: /Route R1 · 1 h 40 min/ });
    expect(bar).toHaveAttribute("aria-expanded", "false");
    await user.click(bar);
    expect(bar).toHaveAttribute("aria-expanded", "true");
  });

  it("opens the sheet again when planning fails", async () => {
    const plan = vi.fn<ApiClient["plan"]>(() =>
      Promise.reject(new ApiError({ code: "NO_ROUTE", message: "x", status: 422 })),
    );
    const { user } = renderApp({ plan });
    await user.click(screen.getByRole("button", { name: /Trip details/ })); // the person closed it
    expect(screen.getByRole("button", { name: /Trip details/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    await user.click(screen.getByRole("button", { name: "Plan trip", hidden: true }));

    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: /Trip details/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});

describe("a slow or absent server", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("says nothing before three seconds, then that the server is waking up", async () => {
    renderApp({ health: () => new Promise(() => undefined) });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2999);
    });
    expect(screen.queryByText("Waking up the server…")).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(screen.getByText("Waking up the server…")).toBeInTheDocument();
  });

  it("takes the message away when the server answers", async () => {
    let answer: (value: { status: string }) => void = () => undefined;
    renderApp({
      health: () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(screen.getByText("Waking up the server…")).toBeInTheDocument();

    await act(async () => {
      answer({ status: "ok" });
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(screen.queryByText("Waking up the server…")).not.toBeInTheDocument();
  });

  it("says so when the server never answers", async () => {
    renderApp({
      health: () => Promise.reject(new ApiError({ code: "NETWORK", message: "no", status: 0 })),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });

    expect(screen.getByText(/The server is not answering/)).toBeInTheDocument();
  });
});
