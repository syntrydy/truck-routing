import { afterEach, describe, expect, it } from "vitest";

import { formatMoment, formatHoursAhead, frameTime } from "./forecastTime.ts";

describe("frameTime", () => {
  it("is the start plus one hour per frame", () => {
    expect(frameTime("2026-10-18T19:00:00Z", 0).toISOString()).toBe("2026-10-18T19:00:00.000Z");
    expect(frameTime("2026-10-18T19:00:00Z", 5).toISOString()).toBe("2026-10-19T00:00:00.000Z");
    expect(frameTime("2026-10-18T19:00:00Z", 48).toISOString()).toBe("2026-10-20T19:00:00.000Z");
  });
});

describe("formatMoment", () => {
  it("is the local time with its zone and UTC offset", () => {
    expect(formatMoment(new Date("2026-10-18T23:00:00Z"))).toBe("Sun, 6:00 PM CDT (UTC-05:00)");
  });

  it("follows daylight saving", () => {
    expect(formatMoment(new Date("2026-11-02T18:00:00Z"))).toBe("Mon, 12:00 PM CST (UTC-06:00)");
  });
});

describe("formatMoment in a zone with no abbreviation", () => {
  const original = process.env.TZ;
  afterEach(() => {
    process.env.TZ = original;
  });
  const moment = new Date("2026-10-18T19:00:00Z");

  it.each([
    ["Africa/Douala", "Sun, 8:00 PM UTC+01:00"],
    ["America/Sao_Paulo", "Sun, 4:00 PM UTC-03:00"],
    ["Asia/Kolkata", "Mon, 12:30 AM UTC+05:30"],
  ])("says %s once, as an offset", (zone, expected) => {
    process.env.TZ = zone;

    expect(formatMoment(moment)).toBe(expected);
  });

  it("writes UTC itself once too", () => {
    process.env.TZ = "UTC";

    expect(formatMoment(moment)).toBe("Sun, 7:00 PM UTC+00:00");
  });
});

describe("formatHoursAhead", () => {
  it.each([
    [0, "+0 h"],
    [1, "+1 h"],
    [48, "+48 h"],
  ])("writes %d as %s", (hour, text) => {
    expect(formatHoursAhead(hour)).toBe(text);
  });
});
