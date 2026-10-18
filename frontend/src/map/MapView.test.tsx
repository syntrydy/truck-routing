import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ATTRIBUTION, INITIAL_CENTER, INITIAL_ZOOM, MAP_STYLE_URL } from "./config.ts";
import { fake, fakeMapLibreModule } from "./fakeMapLibre.ts";
import { MapView } from "./MapView.tsx";
import { preloadMapLibre } from "./useMap.ts";

const idleProps = {
  plan: null,
  selection: { selectedId: null, hoveredId: null },
  onSelectRoute: () => undefined,
  onHoverRoute: () => undefined,
  forecast: { frames: null, hour: 0 },
};
import userEvent from "@testing-library/user-event";

vi.mock("maplibre-gl", () => fakeMapLibreModule);

beforeEach(() => {
  fake.reset();
});

async function mapCreated() {
  await waitFor(() => {
    expect(fake.maps).toHaveLength(1);
  });
  return fake.maps[0];
}

describe("MapView", () => {
  it("shows a loading message, then the map", async () => {
    render(<MapView {...idleProps} />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading the map");
    await mapCreated();
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  it("shares the load that was started ahead of the app: one map, never an error", async () => {
    preloadMapLibre();
    preloadMapLibre();

    render(<MapView {...idleProps} />);

    await mapCreated();
    expect(fake.maps).toHaveLength(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("creates the map in its container, centred on the United States", async () => {
    render(<MapView {...idleProps} />);

    const map = await mapCreated();

    expect(map?.options.container).toBe(screen.getByTestId("map-canvas"));
    expect(map?.options).toMatchObject({
      style: MAP_STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      attributionControl: false,
    });
  });

  it("shows the credit of the routing and weather data, expanded", async () => {
    render(<MapView {...idleProps} />);
    await mapCreated();

    expect(fake.attributionOptions).toEqual([
      { compact: false, customAttribution: [...ATTRIBUTION] },
    ]);
    const credit = ATTRIBUTION.join(" ");
    for (const name of ["OSRM", "Open-Meteo", "CC BY 4.0"]) {
      expect(credit).toContain(name);
    }
  });

  it("adds zoom buttons without the compass", async () => {
    render(<MapView {...idleProps} />);

    const map = await mapCreated();

    const navigation = map?.controls.find(({ position }) => position === "top-right");
    expect(navigation?.control).toMatchObject({ options: { showCompass: false } });
  });

  it("is not created again when the page around it re-renders", async () => {
    function Page() {
      const [count, setCount] = useState(0);
      return (
        <>
          <button
            onClick={() => {
              setCount(count + 1);
            }}
          >
            clicked {count}
          </button>
          <MapView {...idleProps} />
        </>
      );
    }
    const user = userEvent.setup();
    render(<Page />);
    await mapCreated();

    await user.click(screen.getByRole("button"));
    await user.click(screen.getByRole("button"));

    expect(screen.getByRole("button")).toHaveTextContent("clicked 2");
    expect(fake.maps).toHaveLength(1);
    expect(fake.maps[0]?.remove).not.toHaveBeenCalled();
  });

  it("is created once even when React mounts it twice in development", async () => {
    render(
      <StrictMode>
        <MapView {...idleProps} />
      </StrictMode>,
    );

    await mapCreated();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(fake.maps).toHaveLength(1);
  });

  it("removes the map when it goes away", async () => {
    const { unmount } = render(<MapView {...idleProps} />);
    const map = await mapCreated();

    unmount();

    expect(map?.remove).toHaveBeenCalledTimes(1);
  });

  it("creates no map when it goes away before MapLibre has loaded", async () => {
    const { unmount } = render(<MapView {...idleProps} />);
    unmount();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(fake.maps).toHaveLength(0);
  });

  it("says so when the map cannot start", async () => {
    fake.failOnCreate = true;

    render(<MapView {...idleProps} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
