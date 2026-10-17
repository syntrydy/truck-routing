import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiWrapper, stubClient } from "./api/testing.tsx";
import type { ApiClient } from "./api/client.ts";
import { App } from "./App.tsx";
import { fake, fakeMapLibreModule } from "./map/fakeMapLibre.ts";
import { samplePlan } from "./test/plan.ts";
import { CHICAGO, DENVER } from "./test/places.ts";

vi.mock("maplibre-gl", () => fakeMapLibreModule);

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
      expect(fake.maps[0]?.layers).toHaveLength(5);
    });
    const map = fake.maps[0];

    for (const [name, typed] of [
      ["From", "chicago"],
      ["To", "denver"],
    ] as const) {
      await user.type(screen.getByRole("combobox", { name }), typed);
      await screen.findByRole("option");
      await user.keyboard("{ArrowDown}{Enter}");
    }
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
      expect(fake.maps[0]?.layers).toHaveLength(5);
    });
    const map = fake.maps[0];
    for (const [name, typed] of [
      ["From", "chicago"],
      ["To", "denver"],
    ] as const) {
      await user.type(screen.getByRole("combobox", { name }), typed);
      await screen.findByRole("option");
      await user.keyboard("{ArrowDown}{Enter}");
    }
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
      expect(fake.maps[0]?.layers).toHaveLength(5);
    });
    for (const [name, typed] of [
      ["From", "chicago"],
      ["To", "denver"],
    ] as const) {
      await user.type(screen.getByRole("combobox", { name }), typed);
      await screen.findByRole("option");
      await user.keyboard("{ArrowDown}{Enter}");
    }
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
      expect(fake.maps[0]?.layers).toHaveLength(5);
    });
    for (const [name, typed] of [
      ["From", "chicago"],
      ["To", "denver"],
    ] as const) {
      await context.user.type(screen.getByRole("combobox", { name }), typed);
      await screen.findByRole("option");
      await context.user.keyboard("{ArrowDown}{Enter}");
    }
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
    const { ApiError } = await import("./api/errors.ts");
    const plan = vi.fn<ApiClient["plan"]>(() =>
      Promise.reject(new ApiError({ code: "NO_ROUTE", message: "No drivable route", status: 422 })),
    );
    const { user } = renderApp({ plan });

    for (const [name, typed] of [
      ["From", "chicago"],
      ["To", "denver"],
    ] as const) {
      await user.type(screen.getByRole("combobox", { name }), typed);
      await screen.findByRole("option");
      await user.keyboard("{ArrowDown}{Enter}");
    }
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Plan trip" }));
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No drivable route");
  });
});
