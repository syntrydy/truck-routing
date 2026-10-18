import { expect, test, type Page } from "@playwright/test";

/** A basemap with nothing in it: the test is about the page, and needs no tile server. */
const EMPTY_STYLE = { version: 8, sources: {}, layers: [] };

/** The screens the app is for: a phone, a tablet, held both ways, and a small laptop. */
const SCREENS = [
  { name: "small phone", width: 360, height: 640, touch: true, cramped: true },
  { name: "phone", width: 390, height: 844, touch: true, cramped: true },
  { name: "tablet held upright", width: 768, height: 1024, touch: true, cramped: true },
  { name: "large tablet held upright", width: 820, height: 1180, touch: true, cramped: true },
  { name: "phone held sideways", width: 844, height: 390, touch: true, cramped: true },
  { name: "tablet held sideways", width: 1024, height: 768, touch: true, cramped: false },
  { name: "small laptop", width: 1000, height: 700, touch: false, cramped: false },
] as const;

/** The phone layout, with the map on top and the trip sheet below. */
const SHEET_LAYOUT = new Set([
  "small phone",
  "phone",
  "tablet held upright",
  "large tablet held upright",
]);

const TOUCH_TARGET_PX = 44;
const MAP_SHARE_MIN = 0.4;

async function noSidewaysScroll(page: Page) {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
}

async function insideScreen(
  page: Page,
  name: string,
  locator = page.getByRole("button", { name }),
) {
  const box = await locator.boundingBox();
  const size = page.viewportSize();
  expect(box, `${name} is on the page`).not.toBeNull();
  expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(size?.width ?? 0);
}

for (const screen of SCREENS) {
  test.describe(screen.name, () => {
    test.use({
      viewport: { width: screen.width, height: screen.height },
      hasTouch: screen.touch,
      isMobile: screen.touch,
    });

    test("fits, before and after a plan", async ({ page }) => {
      await page.route("https://tiles.openfreemap.org/**", (route) =>
        route.fulfill({ json: EMPTY_STYLE }),
      );
      await page.goto("/");
      await page.getByTestId("map-canvas").waitFor();
      await noSidewaysScroll(page);
      await expect(page.getByRole("button", { name: "Try the stormy demo" })).toBeVisible();

      await page.getByRole("button", { name: "Try the stormy demo" }).click();
      await page.getByRole("slider", { name: "Forecast hour" }).waitFor();

      await noSidewaysScroll(page);
      await insideScreen(page, "Play");
      await expect(page.getByText(/UTC[+-]\d\d:\d\d, \+0 h/)).toBeVisible();
      const slider = page.getByRole("slider", { name: "Forecast hour" });
      await insideScreen(page, "the slider", slider);
    });

    test("leaves the map most of the screen", async ({ page }) => {
      await page.route("https://tiles.openfreemap.org/**", (route) =>
        route.fulfill({ json: EMPTY_STYLE }),
      );
      await page.goto("/");
      await page.getByRole("button", { name: "Try the stormy demo" }).click();
      await page.getByRole("slider", { name: "Forecast hour" }).waitFor();

      const map = await page.locator(".shell__map").boundingBox();
      expect((map?.height ?? 0) / screen.height).toBeGreaterThanOrEqual(MAP_SHARE_MIN);
    });

    if (SHEET_LAYOUT.has(screen.name)) {
      test("folds the trip sheet to a bar of one line", async ({ page }) => {
        await page.route("https://tiles.openfreemap.org/**", (route) =>
          route.fulfill({ json: EMPTY_STYLE }),
        );
        await page.goto("/");
        await page.getByRole("button", { name: "Try the stormy demo" }).click();
        await page.getByRole("slider", { name: "Forecast hour" }).waitFor();

        const bar = await page.locator(".sheet-toggle").boundingBox();
        expect(bar?.height ?? 0).toBeLessThanOrEqual(64);
        expect((bar?.y ?? 0) + (bar?.height ?? 0)).toBeLessThanOrEqual(screen.height);
      });
    }

    if (screen.touch) {
      test("has touch targets of at least 44 px", async ({ page }) => {
        await page.route("https://tiles.openfreemap.org/**", (route) =>
          route.fulfill({ json: EMPTY_STYLE }),
        );
        await page.goto("/");
        await page.getByRole("button", { name: "Try the stormy demo" }).click();
        await page.getByRole("slider", { name: "Forecast hour" }).waitFor();

        const targets = [
          page.getByRole("button", { name: /Play|Pause/ }),
          page.locator(".forecast__variables .segmented__option span").first(),
          page.locator(".maplibregl-ctrl-zoom-in"),
        ];
        for (const target of targets) {
          const box = await target.boundingBox();
          expect(box?.height ?? 0).toBeGreaterThanOrEqual(TOUCH_TARGET_PX - 0.5);
        }
      });
    }

    test(
      screen.cramped ? "folds the map credit behind a button" : "shows the map credit",
      async ({ page }) => {
        await page.route("https://tiles.openfreemap.org/**", (route) =>
          route.fulfill({ json: EMPTY_STYLE }),
        );
        await page.goto("/");
        await page.getByTestId("map-canvas").waitFor();

        const credit = page.locator(".maplibregl-ctrl-attrib");
        await expect(credit).toBeVisible();
        if (screen.cramped) {
          await expect(credit).toHaveClass(/maplibregl-compact/);
          await expect(credit).not.toHaveAttribute("open", /.*/);
        } else {
          await expect(credit).not.toHaveClass(/maplibregl-compact/);
        }
      },
    );
  });
}
