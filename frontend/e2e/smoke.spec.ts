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

  await expect(page.getByRole("combobox", { name: "From" })).toHaveValue(/^Chicago/);
  await expect(page.getByRole("combobox", { name: "To" })).toHaveValue(/^Denver/);

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
  // The checkpoint's popup; the summary of the route line under the pointer is a popup too.
  await expect(page.locator(".maplibregl-popup:not(.route-tip-popup)")).toContainText("mph");

  // Move the forecast an hour at a time with the keyboard.
  const slider = page.getByRole("slider", { name: "Forecast hour" });
  await slider.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(slider).toHaveValue("3");
  await expect(slider).toHaveAttribute("aria-valuetext", /\+3 h/);
});

test("the stormy demo shows danger on the fastest road and says it is a recording", async ({
  page,
}) => {
  await page.route("https://tiles.openfreemap.org/**", (route) =>
    route.fulfill({ json: EMPTY_STYLE }),
  );
  await page.goto("/");

  const planned = page.waitForResponse("**/api/demo*");
  await page.getByRole("button", { name: "Try the stormy demo" }).click();
  const plan = (await (await planned).json()) as PlanBody & {
    meta: { weather_source: string };
    routes: { id: string; duration_s: number; summary: { worst_level: string } }[];
  };

  await expect(page.getByText("Demo: a recording, not a live forecast.")).toBeVisible();
  await expect(page.getByText(/^Denver → Salt Lake City · /)).toBeVisible();
  await expect(page.getByRole("heading", { level: 3 })).toHaveCount(3);
  await expect(page.getByText("Recommended", { exact: true })).toHaveCount(1);

  // The storm is on the fastest road, and the recommendation goes around it.
  expect(plan.meta.weather_source).toBe("demo");
  const fastest = [...plan.routes].sort((a, b) => a.duration_s - b.duration_s)[0];
  expect(fastest?.summary.worst_level).toBe("NO_TRAVEL");
  expect(plan.recommended_route_id).not.toBe(fastest?.id);
  await expect(
    page
      .locator(".route-cards")
      .getByText(/No travel/i)
      .first(),
  ).toBeVisible();
});
