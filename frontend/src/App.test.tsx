import { act, render, screen, waitFor, within } from "@testing-library/react";
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
      expect(fake.maps[0]?.layers).toHaveLength(3);
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
