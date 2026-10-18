/**
 * OpenFreeMap's "Bright" style: the same roads, water, borders and labels as its "Liberty"
 * style, without the shaded-relief images that Liberty draws. Those images were about 6 MB of
 * the first load (6.8 MB against 1.3 MB for the page and a demo plan, measured in a browser) and
 * made the map arrive piece by piece on a slow connection (SPEC section 3).
 */
export const DEFAULT_MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/bright";

/** The basemap style; `VITE_MAP_STYLE_URL` picks another. */
export const MAP_STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL ?? DEFAULT_MAP_STYLE_URL;

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
