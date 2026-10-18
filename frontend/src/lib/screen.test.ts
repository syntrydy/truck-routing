import { afterEach, describe, expect, it, vi } from "vitest";

import { isSheetLayout, SHEET_LAYOUT_QUERY, SHORT_SCREEN_QUERY, isCramped } from "./screen.ts";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("isSheetLayout", () => {
  it("asks the browser the same question the stylesheet asks", () => {
    const matchMedia = vi.fn(() => ({ matches: true }));
    vi.stubGlobal("matchMedia", matchMedia);

    expect(isSheetLayout()).toBe(true);
    expect(matchMedia).toHaveBeenCalledWith(SHEET_LAYOUT_QUERY);
  });

  it("is false for a wide screen", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));

    expect(isSheetLayout()).toBe(false);
  });

  it("is false where the browser cannot say", () => {
    vi.stubGlobal("matchMedia", undefined);

    expect(isSheetLayout()).toBe(false);
  });

  it("is the one rule of the stylesheet: a phone, or a tablet held upright", () => {
    expect(SHEET_LAYOUT_QUERY).toBe(
      "(max-width: 50rem), (max-width: 64rem) and (orientation: portrait)",
    );
  });
});

describe("isCramped", () => {
  const screen = (...matching: string[]) =>
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: matching.includes(query) }));

  it.each([
    ["a phone or a tablet held upright", SHEET_LAYOUT_QUERY, true],
    ["a screen with little height", SHORT_SCREEN_QUERY, true],
    ["a roomy screen", "(min-width: 100rem)", false],
  ])("is %s", (_name, query, expected) => {
    screen(query);

    expect(isCramped()).toBe(expected);
  });

  it("is the one rule of the stylesheet: little height", () => {
    expect(SHORT_SCREEN_QUERY).toBe("(max-height: 32rem)");
  });
});
