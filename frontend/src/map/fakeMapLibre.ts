import { vi } from "vitest";

/** What the tests see of MapLibre: every map made, and what was added to it. */
export const fake = {
  maps: [] as FakeMap[],
  popups: [] as FakePopup[],
  markers: [] as FakeMarker[],
  attributionOptions: [] as unknown[],
  failOnCreate: false,
  styleLoaded: true,
  reset() {
    this.maps = [];
    this.popups = [];
    this.markers = [];
    this.attributionOptions = [];
    this.failOnCreate = false;
    this.styleLoaded = true;
  },
};

type Handler = (event: unknown) => void;

export class FakeSource {
  data: unknown;
  readonly setData = vi.fn((data: unknown) => {
    this.data = data;
    return Promise.resolve(this);
  });

  constructor(readonly spec: { data?: unknown }) {
    this.data = spec.data;
  }
}

export class FakeMap {
  readonly controls: { control: unknown; position: string | undefined }[] = [];
  readonly sources = new Map<string, FakeSource>();
  readonly layers: { id: string; type: string; source: string; before?: string }[] = [];
  /** The basemap's own layers: water, then the place names. */
  readonly baseLayers = [
    { id: "water", type: "fill" },
    { id: "place-labels", type: "symbol" },
  ];
  readonly handlers = new Map<string, Handler[]>();
  readonly remove = vi.fn();
  readonly fitBounds = vi.fn();
  readonly canvas = { style: { cursor: "" } };

  constructor(readonly options: Record<string, unknown>) {
    if (fake.failOnCreate) {
      throw new Error("Failed to initialize WebGL");
    }
    fake.maps.push(this);
  }

  addControl(control: unknown, position?: string) {
    this.controls.push({ control, position });
  }

  /** The style once its JSON is in, `undefined` before (as MapLibre does). */
  getStyle() {
    return fake.styleLoaded ? { layers: [...this.baseLayers, ...this.layers] } : undefined;
  }

  getCanvas() {
    return this.canvas;
  }

  addSource(id: string, spec: { data?: unknown }) {
    this.sources.set(id, new FakeSource(spec));
  }

  getSource(id: string) {
    return this.sources.get(id);
  }

  addLayer(layer: { id: string; type: string; source: string }, before?: string) {
    this.layers.push(before === undefined ? layer : { ...layer, before });
  }

  /** `on(type, listener)` or `on(type, layerId, listener)`, as in MapLibre. */
  on(type: string, layerOrListener: string | Handler, listener?: Handler) {
    const [key, handler] =
      typeof layerOrListener === "string"
        ? [`${type}:${layerOrListener}`, listener]
        : [type, layerOrListener];
    if (handler !== undefined) {
      this.handlers.set(key, [...(this.handlers.get(key) ?? []), handler]);
    }
  }

  once(type: string, listener: Handler) {
    this.on(type, listener);
  }

  off(type: string, layerOrListener: string | Handler, listener?: Handler) {
    const [key, handler] =
      typeof layerOrListener === "string"
        ? [`${type}:${layerOrListener}`, listener]
        : [type, layerOrListener];
    this.handlers.set(
      key,
      (this.handlers.get(key) ?? []).filter((existing) => existing !== handler),
    );
  }

  /** Fires what was registered for `type` (and `layer`), like the real map would. */
  emit(type: string, layerOrEvent?: unknown, event?: unknown) {
    const [key, payload] =
      typeof layerOrEvent === "string" ? [`${type}:${layerOrEvent}`, event] : [type, layerOrEvent];
    for (const handler of this.handlers.get(key) ?? []) {
      handler(payload);
    }
  }
}

export class FakePopup {
  lngLat: [number, number] | null = null;
  content: HTMLElement | null = null;
  readonly remove = vi.fn();

  constructor(readonly options: unknown) {
    fake.popups.push(this);
  }

  setLngLat(lngLat: [number, number]) {
    this.lngLat = lngLat;
    return this;
  }

  setDOMContent(content: HTMLElement) {
    this.content = content;
    return this;
  }

  addTo() {
    return this;
  }
}

export class FakeMarker {
  lngLat: [number, number] | null = null;
  added = false;
  readonly remove = vi.fn(() => {
    this.added = false;
  });

  constructor(readonly options: { element?: HTMLElement }) {
    fake.markers.push(this);
  }

  setLngLat(lngLat: [number, number]) {
    this.lngLat = lngLat;
    return this;
  }

  addTo() {
    this.added = true;
    return this;
  }
}

export class FakeAttributionControl {
  readonly options: unknown;

  constructor(options: unknown) {
    this.options = options;
    fake.attributionOptions.push(options);
  }
}

export class FakeNavigationControl {
  readonly options: unknown;

  constructor(options: unknown) {
    this.options = options;
  }
}

/** The module `vi.mock("maplibre-gl", ...)` should return. */
export const fakeMapLibreModule = {
  Map: FakeMap,
  Popup: FakePopup,
  Marker: FakeMarker,
  AttributionControl: FakeAttributionControl,
  NavigationControl: FakeNavigationControl,
};
