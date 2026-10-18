import { afterEach, describe, expect, it } from "vitest";

import { focusIfLost } from "./focus.ts";

afterEach(() => {
  document.body.replaceChildren();
});

function button(label: string): HTMLButtonElement {
  const element = document.createElement("button");
  element.textContent = label;
  document.body.append(element);
  return element;
}

describe("focusIfLost", () => {
  it("takes focus when it is on the page body", () => {
    const target = button("target");
    expect(document.activeElement).toBe(document.body);

    focusIfLost(target);

    expect(document.activeElement).toBe(target);
  });

  it("leaves focus where it is when it is on a real element", () => {
    const other = button("other");
    const target = button("target");
    other.focus();

    focusIfLost(target);

    expect(document.activeElement).toBe(other);
  });

  it("does nothing without a target", () => {
    expect(() => {
      focusIfLost(null);
    }).not.toThrow();
  });
});
