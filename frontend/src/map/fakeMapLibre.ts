import { vi } from "vitest";

/** What the tests see of MapLibre: every map made, and what was added to it. */
export const fake = {
  maps: [] as FakeMap[],
  attributionOptions: [] as unknown[],
  failOnCreate: false,
  reset() {
    this.maps = [];
    this.attributionOptions = [];
    this.failOnCreate = false;
  },
};

export class FakeMap {
  readonly controls: { control: unknown; position: string | undefined }[] = [];
  readonly remove = vi.fn();

  constructor(readonly options: Record<string, unknown>) {
    if (fake.failOnCreate) {
      throw new Error("Failed to initialize WebGL");
    }
    fake.maps.push(this);
  }

  addControl(control: unknown, position?: string) {
    this.controls.push({ control, position });
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
  AttributionControl: FakeAttributionControl,
  NavigationControl: FakeNavigationControl,
};
