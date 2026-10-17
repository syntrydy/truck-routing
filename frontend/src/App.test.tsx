import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiWrapper, stubClient } from "./api/testing.tsx";
import { App } from "./App.tsx";
import { fake, fakeMapLibreModule } from "./map/fakeMapLibre.ts";

vi.mock("maplibre-gl", () => fakeMapLibreModule);

beforeEach(() => {
  fake.reset();
});

function renderApp(health = vi.fn(() => Promise.resolve({ status: "ok" }))) {
  render(<App />, { wrapper: apiWrapper(stubClient({ health })) });
  return health;
}

describe("App", () => {
  it("renders the application title", () => {
    renderApp();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Weather-Aware Truck Routing",
    );
  });

  it("warms the server up on load", async () => {
    const health = renderApp();

    await waitFor(() => {
      expect(health).toHaveBeenCalledTimes(1);
    });
  });

  it("puts the map in the page", async () => {
    renderApp();

    await waitFor(() => {
      expect(fake.maps).toHaveLength(1);
    });
    expect(screen.getByRole("main")).toContainElement(screen.getByTestId("map-canvas"));
  });
});
