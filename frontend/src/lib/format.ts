const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;
const WHOLE_MILES_FROM = 100;

/** A drive time such as `17 h 5 min`, `2 h` or `45 min`, rounded to the minute. */
export function formatDuration(seconds: number): string {
  const totalMinutes = Math.max(0, Math.round(seconds / SECONDS_PER_MINUTE));
  const hours = Math.floor(totalMinutes / MINUTES_PER_HOUR);
  const minutes = totalMinutes % MINUTES_PER_HOUR;
  if (hours === 0) {
    return `${String(minutes)} min`;
  }
  return minutes === 0 ? `${String(hours)} h` : `${String(hours)} h ${String(minutes)} min`;
}

/** Miles with thousands separators; tenths only for short distances, e.g. `1,003 mi`, `42.5 mi`. */
export function formatMiles(miles: number): string {
  const digits = miles >= WHOLE_MILES_FROM ? 0 : 1;
  return `${miles.toLocaleString("en-US", { maximumFractionDigits: digits })} mi`;
}
