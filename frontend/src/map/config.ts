/** OpenFreeMap's free vector style (SPEC section 3). Override with `VITE_MAP_STYLE_URL`. */
export const MAP_STYLE_URL =
  import.meta.env.VITE_MAP_STYLE_URL ?? "https://tiles.openfreemap.org/styles/liberty";

/** [longitude, latitude] of the contiguous United States, the area the app is meant for. */
export const INITIAL_CENTER: [number, number] = [-98.5, 39.8];
export const INITIAL_ZOOM = 3.6;

/**
 * Credit for the data behind what is drawn on top of the basemap. The basemap's own credit
 * (OpenStreetMap contributors, OpenFreeMap, OpenMapTiles) comes with its style, so it is not
 * repeated here.
 */
export const ATTRIBUTION: readonly string[] = [
  '<a href="https://project-osrm.org" target="_blank" rel="noreferrer">OSRM</a>',
  '<a href="https://open-meteo.com" target="_blank" rel="noreferrer">Weather data by Open-Meteo.com (CC BY 4.0)</a>',
];
