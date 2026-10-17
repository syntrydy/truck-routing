import { describe, expect, it } from "vitest";

import { formatFrameTime, formatHoursAhead, frameTime } from "./forecastTime.ts";

describe("frameTime", () => {
  it("is the start plus one hour per frame", () => {
    expect(frameTime("2026-10-18T19:00:00Z", 0).toISOString()).toBe("2026-10-18T19:00:00.000Z");
    expect(frameTime("2026-10-18T19:00:00Z", 5).toISOString()).toBe("2026-10-19T00:00:00.000Z");
    expect(frameTime("2026-10-18T19:00:00Z", 48).toISOString()).toBe("2026-10-20T19:00:00.000Z");
  });
});

describe("formatFrameTime", () => {
  it("is the local time with its zone and UTC offset", () => {
    expect(formatFrameTime(new Date("2026-10-18T23:00:00Z"))).toBe("Sun, 6:00 PM CDT (UTC-05:00)");
  });

  it("follows daylight saving", () => {
    expect(formatFrameTime(new Date("2026-11-02T18:00:00Z"))).toBe("Mon, 12:00 PM CST (UTC-06:00)");
  });
});

describe("formatHoursAhead", () => {
  it.each([
    [0, "at departure"],
    [1, "+1 h"],
    [48, "+48 h"],
  ])("writes %d as %s", (hour, text) => {
    expect(formatHoursAhead(hour)).toBe(text);
  });
});
