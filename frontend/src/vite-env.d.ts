/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Origin of the API; unset means the same origin (the dev server proxies /api). */
  readonly VITE_API_BASE_URL?: string;
  /** Style URL of the basemap; defaults to OpenFreeMap. */
  readonly VITE_MAP_STYLE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
