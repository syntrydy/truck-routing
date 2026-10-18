import { expect, test, type Page } from "@playwright/test";

interface PlanBody {
  recommended_route_id: string;
  routes: { id: string; checkpoints: { lat: number; lon: number }[] }[];
}

interface TestWindow {
  __truckMap: {
    isMoving: () => boolean;
    getLayer: (id: string) => unknown;
    project: (lngLat: [number, number]) => { x: number; y: number };
  };
}

/** A basemap with nothing in it: the test is about our layers, and needs no tile server. */
const EMPTY_STYLE = { version: 8, sources: {}, layers: [] };

async function chooseTrip(page: Page, field: string, typed: string) {
  await page.getByRole("combobox", { name: field }).fill(typed);
  await page.getByRole("option").first().waitFor();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
}

test("plans a trip, opens a checkpoint and moves the forecast", async ({ page }) => {
  await page.route("https://tiles.openfreemap.org/**", (route) =>
    route.fulfill({ json: EMPTY_STYLE }),
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Weather-Aware Truck Routing");

  await chooseTrip(page, "From", "boulder");
  await chooseTrip(page, "To", "fort collins");
  const planned = page.waitForResponse("**/api/plan");
  await page.getByRole("button", { name: "Plan trip" }).click();
  const plan = (await (await planned).json()) as PlanBody;

  // The recorded server offered two routes for this trip.
  await expect(page.getByRole("heading", { level: 2, name: "Routes" })).toBeFocused();
  await expect(page.getByRole("heading", { level: 3 })).toHaveCount(plan.routes.length);
  await expect(page.getByText("Recommended", { exact: true })).toHaveCount(1);

  // Click a checkpoint of the recommended route where the map draws it.
  const route = plan.routes.find((candidate) => candidate.id === plan.recommended_route_id);
  const checkpoint = route?.checkpoints[Math.floor((route.checkpoints.length - 1) / 2)];
  expect(checkpoint).toBeDefined();
  await page.waitForFunction(() => {
    const map = (window as unknown as TestWindow).__truckMap;
    return !map.isMoving() && map.getLayer("checkpoints") !== undefined;
  });
  const point = await page.evaluate(
    ([lon, lat]) => (window as unknown as TestWindow).__truckMap.project([lon, lat]),
    [checkpoint?.lon ?? 0, checkpoint?.lat ?? 0] as [number, number],
  );
  const canvas = await page.getByTestId("map-canvas").boundingBox();
  await page.mouse.click((canvas?.x ?? 0) + point.x, (canvas?.y ?? 0) + point.y);
  await expect(page.locator(".maplibregl-popup")).toContainText("mph");

  // Move the forecast an hour at a time with the keyboard.
  const slider = page.getByRole("slider", { name: "Forecast hour" });
  await slider.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(slider).toHaveValue("3");
  await expect(slider).toHaveAttribute("aria-valuetext", /\+3 h/);
});
