import { toOffsetIso } from "./trip.ts";

const HOUR_MS = 60 * 60 * 1000;

/** The moment of frame `hour`: the heatmap starts at `startIso` and has one frame per hour. */
export function frameTime(startIso: string, hour: number): Date {
  return new Date(new Date(startIso).getTime() + hour * HOUR_MS);
}

/** The reader's local time with its zone and UTC offset, e.g. `Sun, 6:00 PM CDT (UTC-05:00)`. */
export function formatFrameTime(moment: Date): string {
  const text = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(moment);
  return `${text} (UTC${toOffsetIso(moment).slice(-6)})`;
}

/** How far the frame is from departure, e.g. `now`, `+3 h`. */
export function formatHoursAhead(hour: number): string {
  return hour === 0 ? "at departure" : `+${String(hour)} h`;
}
