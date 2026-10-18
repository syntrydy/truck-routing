import { describe, expect, it } from "vitest";

import { CHICAGO, DENVER, NOW } from "../test/places.ts";
import {
  DEFAULT_DESTINATION,
  DEFAULT_ORIGIN,
  defaultTripValues,
  formatLocalInput,
  isStale,
  parseLoad,
  parseLocalInput,
  timeZoneLabel,
  toOffsetIso,
  toPlanRequest,
  withDemoTrip,
  validateTrip,
  type TripValues,
} from "./trip.ts";

function valid(changes: Partial<TripValues> = {}): TripValues {
  return { ...defaultTripValues(NOW), origin: CHICAGO, destination: DENVER, ...changes };
}

const minutesFromNow = (minutes: number) =>
  formatLocalInput(new Date(NOW.getTime() + minutes * 60_000));

describe("defaultTripValues", () => {
  it("plans Chicago to Denver, leaving at the next full hour, with 42,000 lb and checkpoints every 25 miles", () => {
    expect(defaultTripValues(NOW)).toEqual({
      origin: DEFAULT_ORIGIN,
      destination: DEFAULT_DESTINATION,
      departure: "2026-10-18T14:00",
      load: "42000",
      interval: 25,
    });
  });

  it("makes a request that needs no further input", () => {
    expect(toPlanRequest(defaultTripValues(NOW), NOW)).not.toBeNull();
  });

  it("moves to the next hour even on the hour", () => {
    expect(defaultTripValues(new Date(2026, 9, 18, 23, 0)).departure).toBe("2026-10-19T00:00");
  });
});

describe("time conversion", () => {
  it("reads and writes the datetime-local text", () => {
    const date = parseLocalInput("2026-10-18T06:05");

    expect(date).toEqual(new Date(2026, 9, 18, 6, 5));
    expect(formatLocalInput(date as Date)).toBe("2026-10-18T06:05");
  });

  it.each(["", "2026-10-18", "2026-10-18T25:00", "tomorrow", "2026-13-01T10:00"])(
    "refuses %j",
    (text) => {
      expect(parseLocalInput(text)).toBeNull();
    },
  );

  it("adds the UTC offset in force at that moment", () => {
    expect(toOffsetIso(new Date(2026, 9, 18, 6, 0))).toBe("2026-10-18T06:00:00-05:00"); // CDT
    expect(toOffsetIso(new Date(2026, 10, 2, 6, 0))).toBe("2026-11-02T06:00:00-06:00"); // CST
  });

  it("names the time zone and its offset", () => {
    expect(timeZoneLabel(new Date(2026, 9, 18, 6, 0))).toBe("America/Chicago (UTC-05:00)");
  });
});

describe("parseLoad", () => {
  it.each([
    ["0", 0],
    ["42000", 42_000],
    [" 80000 ", 80_000],
    ["200000", 200_000],
  ])("reads %j as %d", (text, load) => {
    expect(parseLoad(text)).toBe(load);
  });

  it.each(["", "abc", "-1", "1.5", "1e3", "200001", "42,000", "0x10"])("refuses %j", (text) => {
    expect(parseLoad(text)).toBeNull();
  });
});

describe("validateTrip", () => {
  it("accepts a complete trip", () => {
    expect(validateTrip(valid(), NOW)).toEqual({});
  });

  it("asks for both places", () => {
    const errors = validateTrip(valid({ origin: null, destination: null }), NOW);

    expect(errors.origin).toContain("starting place");
    expect(errors.destination).toContain("destination");
  });

  it("wants the places at least a mile apart", () => {
    const nearby = { ...CHICAGO, lat: CHICAGO.lat + 0.005 }; // about 0.35 mi
    const farEnough = { ...CHICAGO, lat: CHICAGO.lat + 0.02 }; // about 1.4 mi

    expect(validateTrip(valid({ destination: nearby }), NOW).destination).toContain("1 mile");
    expect(validateTrip(valid({ destination: farEnough }), NOW)).toEqual({});
  });

  it("does not report distance while a place is missing", () => {
    expect(validateTrip(valid({ origin: null }), NOW).destination).toBeUndefined();
  });

  it.each([
    [-15, undefined],
    [-16, "15 minutes in the past"],
    [0, undefined],
    [7 * 24 * 60, undefined],
    [7 * 24 * 60 + 1, "next 7 days"],
  ])("departure %d minutes from now: %s", (minutes, message) => {
    const errors = validateTrip(valid({ departure: minutesFromNow(minutes) }), NOW);

    if (message === undefined) {
      expect(errors.departure).toBeUndefined();
    } else {
      expect(errors.departure).toContain(message);
    }
  });

  it("wants a departure", () => {
    expect(validateTrip(valid({ departure: "" }), NOW).departure).toContain("Enter a departure");
  });

  it.each([
    ["", "Enter the load"],
    ["heavy", "whole number"],
    ["200001", "whole number"],
    ["12.5", "whole number"],
  ])("load %j: %s", (load, message) => {
    expect(validateTrip(valid({ load }), NOW).load).toContain(message);
  });
});

describe("toPlanRequest", () => {
  it("builds the request the API expects", () => {
    expect(toPlanRequest(valid({ departure: "2026-10-19T06:00", interval: 50 }), NOW)).toEqual({
      origin: { lat: CHICAGO.lat, lon: CHICAGO.lon, label: CHICAGO.label },
      destination: { lat: DENVER.lat, lon: DENVER.lon, label: DENVER.label },
      departure_at: "2026-10-19T06:00:00-05:00",
      load_lb: 42_000,
      interval_mi: 50,
    });
  });

  it("sends only what the API takes from a place", () => {
    const request = toPlanRequest(valid(), NOW);

    expect(Object.keys(request?.origin ?? {}).sort()).toEqual(["label", "lat", "lon"]);
  });

  it("is null while the form has a problem", () => {
    expect(toPlanRequest(valid({ load: "x" }), NOW)).toBeNull();
    expect(toPlanRequest(valid({ origin: null }), NOW)).toBeNull();
  });
});

describe("isStale", () => {
  const planned = toPlanRequest(valid(), NOW);
  const changed = (changes: Partial<TripValues>) => toPlanRequest(valid(changes), NOW);

  it("is false before any plan", () => {
    expect(isStale(null, planned)).toBe(false);
    expect(isStale(null, null)).toBe(false);
  });

  it("is false while nothing changed", () => {
    expect(isStale(planned, changed({}))).toBe(false);
  });

  it.each([
    ["the load", { load: "30000" }],
    ["the spacing", { interval: 10 as const }],
    ["the departure", { departure: "2026-10-19T08:00" }],
    ["the start", { origin: { ...CHICAGO, lat: 41.9 } }],
    ["the destination", { destination: { ...DENVER, label: "Denver" } }],
  ])("is true once %s changes", (_name, change) => {
    expect(isStale(planned, changed(change))).toBe(true);
  });

  it("is true while the form is incomplete after a plan", () => {
    expect(isStale(planned, null)).toBe(true);
  });
});

describe("withDemoTrip", () => {
  it("sets the recorded trip, leaving now, and keeps the load and the spacing", () => {
    const values = { ...defaultTripValues(NOW), load: "36000", interval: 50 as const };

    const demo = withDemoTrip(values, NOW);

    expect(demo.origin?.label).toBe(DENVER.label);
    expect(demo.destination?.label).toBe("Salt Lake City, Utah, United States");
    expect(demo.departure).toBe("2026-10-18T13:20");
    expect(demo.load).toBe("36000");
    expect(demo.interval).toBe(50);
  });
});
