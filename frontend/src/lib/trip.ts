import type { PlanRequest, Place } from "../api/types.ts";

/** The checkpoint spacings the API accepts, in miles. */
export const INTERVALS = [10, 25, 50] as const;
export type Interval = (typeof INTERVALS)[number];

export const DEFAULT_LOAD_LB = 42_000;
export const MAX_LOAD_LB = 200_000;
/** Above this the API adds a note that the load exceeds the usual legal limit. */
export const HEAVY_LOAD_LB = 80_000;
export const DEFAULT_INTERVAL_MI: Interval = 25;

/** The trip the form starts with: SPEC section 5's example, a long run across the plains. */
export const DEFAULT_ORIGIN: Place = {
  label: "Chicago, Illinois, United States",
  lat: 41.8781,
  lon: -87.6298,
  kind: "city",
};
export const DEFAULT_DESTINATION: Place = {
  label: "Denver, Colorado, United States",
  lat: 39.7392,
  lon: -104.9903,
  kind: "city",
};

const MINUTE_MS = 60_000;
const DAY_MS = 24 * 60 * MINUTE_MS;
export const PAST_GRACE_MS = 15 * MINUTE_MS;
export const MAX_LEAD_MS = 7 * DAY_MS;
export const MIN_TRIP_MI = 1;

const EARTH_RADIUS_MI = 3958.8;
const MINUTES_PER_HOUR = 60;

/** What the form holds. `departure` and `load` are the raw text of their inputs. */
export interface TripValues {
  origin: Place | null;
  destination: Place | null;
  /** The value of a `datetime-local` input: local time, `YYYY-MM-DDTHH:mm`. */
  departure: string;
  load: string;
  interval: Interval;
}

export type TripField = "origin" | "destination" | "departure" | "load";
export type TripErrors = Partial<Record<TripField, string>>;

const pad = (value: number) => String(value).padStart(2, "0");

/** The `datetime-local` text for `date`, in the browser's time zone. */
export function formatLocalInput(date: Date): string {
  return (
    `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** The form to start with: the default trip, leaving at the next full hour. */
export function defaultTripValues(now: Date): TripValues {
  const nextHour = new Date(now);
  nextHour.setHours(now.getHours() + 1, 0, 0, 0);
  return {
    origin: DEFAULT_ORIGIN,
    destination: DEFAULT_DESTINATION,
    departure: formatLocalInput(nextHour),
    load: String(DEFAULT_LOAD_LB),
    interval: DEFAULT_INTERVAL_MI,
  };
}

/** The moment a `datetime-local` text means in the browser's time zone; `null` if unusable. */
export function parseLocalInput(text: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(text)) {
    return null;
  }
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** `date` as ISO 8601 with the browser's UTC offset at that moment, e.g. `…T06:00:00-05:00`. */
export function toOffsetIso(date: Date): string {
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes < 0 ? "-" : "+";
  const absolute = Math.abs(offsetMinutes);
  const offset = `${sign}${pad(Math.floor(absolute / MINUTES_PER_HOUR))}:${pad(absolute % MINUTES_PER_HOUR)}`;
  return `${formatLocalInput(date)}:${pad(date.getSeconds())}${offset}`;
}

/** The time zone the departure is read in, such as `America/Chicago (UTC-05:00)`. */
export function timeZoneLabel(date: Date): string {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return `${zone} (UTC${toOffsetIso(date).slice(-6)})`;
}

function distanceMiles(a: Place, b: Place): number {
  const toRadians = Math.PI / 180;
  const dLat = (b.lat - a.lat) * toRadians;
  const dLon = (b.lon - a.lon) * toRadians;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * toRadians) * Math.cos(b.lat * toRadians) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(h));
}

/** The load in pounds when `text` is a whole number from 0 to 200,000, otherwise `null`. */
export function parseLoad(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) {
    return null;
  }
  const load = Number(text);
  return load <= MAX_LOAD_LB ? load : null;
}

/** The problems with `values`, by field, using the same rules as the API (SPEC section 5). */
export function validateTrip(values: TripValues, now: Date): TripErrors {
  const errors: TripErrors = {};
  if (values.origin === null) {
    errors.origin = "Choose a starting place from the list";
  }
  if (values.destination === null) {
    errors.destination = "Choose a destination from the list";
  } else if (
    values.origin !== null &&
    distanceMiles(values.origin, values.destination) < MIN_TRIP_MI
  ) {
    errors.destination = "The destination must be at least 1 mile from the start";
  }

  const departure = parseLocalInput(values.departure);
  if (departure === null) {
    errors.departure = "Enter a departure date and time";
  } else if (departure.getTime() < now.getTime() - PAST_GRACE_MS) {
    errors.departure = "Departure can be at most 15 minutes in the past";
  } else if (departure.getTime() > now.getTime() + MAX_LEAD_MS) {
    errors.departure = "Departure must be within the next 7 days; forecasts do not reach further";
  }

  if (values.load.trim() === "") {
    errors.load = "Enter the load in pounds";
  } else if (parseLoad(values.load) === null) {
    errors.load = "The load must be a whole number of pounds from 0 to 200,000";
  }
  return errors;
}

/** The API request for valid `values`; `null` while anything is missing or wrong. */
export function toPlanRequest(values: TripValues, now: Date): PlanRequest | null {
  const { origin, destination } = values;
  const departure = parseLocalInput(values.departure);
  const load = parseLoad(values.load);
  if (
    origin === null ||
    destination === null ||
    departure === null ||
    load === null ||
    Object.keys(validateTrip(values, now)).length > 0
  ) {
    return null;
  }
  const point = ({ lat, lon, label }: Place) => ({ lat, lon, label });
  return {
    origin: point(origin),
    destination: point(destination),
    departure_at: toOffsetIso(departure),
    load_lb: load,
    interval_mi: values.interval,
  };
}

/** Whether the inputs differ from the ones the shown plan was made for. */
export function isStale(planned: PlanRequest | null, current: PlanRequest | null): boolean {
  if (planned === null) {
    return false;
  }
  if (current === null) {
    return true;
  }
  const samePoint = (a: PlanRequest["origin"], b: PlanRequest["origin"]) =>
    a.lat === b.lat && a.lon === b.lon && a.label === b.label;
  return !(
    samePoint(planned.origin, current.origin) &&
    samePoint(planned.destination, current.destination) &&
    planned.departure_at === current.departure_at &&
    planned.load_lb === current.load_lb &&
    planned.interval_mi === current.interval_mi
  );
}
