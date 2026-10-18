import { toOffsetIso } from "./trip.ts";

const HOUR_MS = 60 * 60 * 1000;

/** The moment of frame `hour`: the heatmap starts at `startIso` and has one frame per hour. */
export function frameTime(startIso: string, hour: number): Date {
  return new Date(new Date(startIso).getTime() + hour * HOUR_MS);
}

/** A short zone name that is only an offset (`GMT+1`, `UTC-3`) or none at all (`UTC`, `GMT`). */
const OFFSET_ONLY_ZONE = /^(GMT|UTC)([+\-\u2212].*)?$/;

/**
 * The reader's local time with its zone, e.g. `Sun, 6:00 PM CDT (UTC-05:00)`. A zone with no
 * abbreviation is named by its offset alone (`Tue, 8:00 PM UTC+01:00`), not twice.
 */
export function formatFrameTime(moment: Date): string {
  const format = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
  const zone = format.formatToParts(moment).find((part) => part.type === "timeZoneName")?.value;
  const offset = `UTC${toOffsetIso(moment).slice(-6)}`;
  const text = format.format(moment);
  if (zone === undefined) {
    return text; // not reached: the format always asks for a zone name
  }
  return text.replace(zone, OFFSET_ONLY_ZONE.test(zone) ? offset : `${zone} (${offset})`);
}

/** How far the frame is from departure, e.g. `now`, `+3 h`. */
export function formatHoursAhead(hour: number): string {
  return hour === 0 ? "at departure" : `+${String(hour)} h`;
}
