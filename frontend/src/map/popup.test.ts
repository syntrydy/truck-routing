import { afterEach, describe, expect, it } from "vitest";

import { checkpoint } from "../test/plan.ts";
import { route as buildRoute } from "../test/plan.ts";
import { buildCheckpointPopup, buildRouteSummary, formatEta, routeSummaryText } from "./popup.ts";

function facts(popup: HTMLElement): Record<string, string> {
  const result: Record<string, string> = {};
  const terms = popup.querySelectorAll("dt");
  const values = popup.querySelectorAll("dd");
  terms.forEach((term, index) => {
    result[term.textContent] = values[index]?.textContent ?? "";
  });
  return result;
}

describe("formatEta", () => {
  it("is the local time with its zone", () => {
    // 19:00 UTC is 14:00 in Chicago on that date (CDT).
    expect(formatEta("2026-10-18T19:00:00Z")).toBe("Sun, Oct 18, 2:00 PM CDT (UTC-05:00)");
  });

  it("follows daylight saving", () => {
    expect(formatEta("2026-11-02T19:00:00Z")).toBe("Mon, Nov 2, 1:00 PM CST (UTC-06:00)");
  });

  describe("in a zone with no abbreviation", () => {
    const original = process.env.TZ;
    afterEach(() => {
      process.env.TZ = original;
    });

    it("writes the zone as the slider does, once, as an offset", () => {
      process.env.TZ = "Africa/Douala";

      expect(formatEta("2026-10-18T19:00:00Z")).toBe("Sun, Oct 18, 8:00 PM UTC+01:00");
    });
  });
});

describe("buildCheckpointPopup", () => {
  it("names the route and the mile, and says the risk in words", () => {
    const popup = buildCheckpointPopup(checkpoint(2, { level: "HIGH" }), "Route A");

    expect(popup.querySelector("h3")?.textContent).toBe("Route A, mile 50");
    expect(popup.querySelector(".popup__level")?.textContent).toBe("Risk: High");
  });

  it.each([
    ["UNKNOWN", "Unknown"],
    ["LOW", "Low"],
    ["MODERATE", "Moderate"],
    ["SEVERE", "Severe"],
    ["NO_TRAVEL", "No travel"],
  ] as const)("writes %s as %s", (level, words) => {
    const popup = buildCheckpointPopup(checkpoint(0, { level }), "Route A");

    expect(popup.querySelector(".popup__level")?.textContent).toBe(`Risk: ${words}`);
  });

  it("shows the arrival and the weather with units", () => {
    const popup = buildCheckpointPopup(
      checkpoint(1, { wind_mph: 31.5, gust_mph: 44, rain_in_hr: 0.12, snow_in_hr: 0 }),
      "Route A",
    );

    expect(facts(popup)).toEqual({
      Arrival: "Sun, Oct 18, 2:00 PM CDT (UTC-05:00)",
      Wind: "31.5 mph",
      Gusts: "44 mph",
      Rain: "0.12 in/hr",
      Snow: "0 in/hr",
    });
  });

  it("says plainly when the weather is not available", () => {
    const popup = buildCheckpointPopup(
      checkpoint(1, {
        wind_mph: null,
        gust_mph: null,
        rain_in_hr: null,
        snow_in_hr: null,
        level: "UNKNOWN",
      }),
      "Route A",
    );

    expect(facts(popup)).toMatchObject({
      Wind: "not available",
      Gusts: "not available",
      Rain: "not available",
      Snow: "not available",
    });
  });

  it("lists the reasons for the level", () => {
    const popup = buildCheckpointPopup(
      checkpoint(1, { reasons: ["Wind 40 mph → High", "Rain 0.3 in/hr → Moderate"] }),
      "Route A",
    );

    expect([...popup.querySelectorAll("li")].map((item) => item.textContent)).toEqual([
      "Wind 40 mph → High",
      "Rain 0.3 in/hr → Moderate",
    ]);
  });

  it("has no list when there is nothing to explain", () => {
    expect(buildCheckpointPopup(checkpoint(1), "Route A").querySelector("ul")).toBeNull();
  });

  it("shows text from the server as text, never as markup", () => {
    const popup = buildCheckpointPopup(
      checkpoint(1, { reasons: ['<img src=x onerror="alert(1)">'] }),
      "<b>Route</b>",
    );

    expect(popup.querySelector("img")).toBeNull();
    expect(popup.querySelector("b")).toBeNull();
    expect(popup.querySelector("li")?.textContent).toBe('<img src=x onerror="alert(1)">');
    expect(popup.querySelector("h3")?.textContent).toContain("<b>Route</b>");
  });
});

describe("routeSummaryText", () => {
  const base = buildRoute("a", 1, ["LOW"], [[-90, 41]]);
  const risky = {
    ...base,
    label: "Route A",
    distance_mi: 505.2,
    duration_s: 9 * 3600,
    summary: {
      ...base.summary,
      worst_level: "NO_TRAVEL" as const,
      miles_by_level: { LOW: 430, NO_TRAVEL: 75 },
    },
  };

  it("gives the name, the time, the distance and the miles at the worst level", () => {
    expect(routeSummaryText(risky)).toBe("Route A · 9 h · 505 mi · 75 mi No travel");
  });

  it("says Worst: Low for a route with nothing worse", () => {
    const calm = {
      ...risky,
      label: "Route B",
      duration_s: 9 * 3600 + 57 * 60,
      distance_mi: 503,
      summary: { ...risky.summary, worst_level: "LOW" as const },
    };

    expect(routeSummaryText(calm)).toBe("Route B · 9 h 57 min · 503 mi · Worst: Low");
  });

  it("does not claim zero miles at a worst level that has none recorded", () => {
    const odd = { ...risky, summary: { ...risky.summary, miles_by_level: {} } };

    expect(routeSummaryText(odd)).toBe("Route A · 9 h · 505 mi · Worst: No travel");
  });

  it("is a paragraph of plain text, never markup", () => {
    const hostile = { ...risky, label: "<img src=x onerror=alert(1)>" };

    const element = buildRouteSummary(hostile);

    expect(element.className).toBe("route-tip");
    expect(element.querySelector("img")).toBeNull();
    expect(element.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
