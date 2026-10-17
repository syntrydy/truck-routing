import type { Place } from "../api/types.ts";

export const DENVER: Place = {
  label: "Denver, Colorado, United States",
  lat: 39.7392,
  lon: -104.9903,
  kind: "city",
};
export const DENVER_IOWA: Place = {
  label: "Denver, Iowa, United States",
  lat: 42.6697,
  lon: -92.3452,
  kind: "city",
};
export const CHICAGO: Place = {
  label: "Chicago, Illinois, United States",
  lat: 41.8781,
  lon: -87.6298,
  kind: "city",
};

/** Saturday 18 October 2026, 13:20 local time (CDT, UTC-05:00 in the test time zone). */
export const NOW = new Date(2026, 9, 18, 13, 20);
