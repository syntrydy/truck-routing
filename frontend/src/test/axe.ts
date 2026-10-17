import axe from "axe-core";
import { expect } from "vitest";

/** Fails when axe finds an accessibility violation in `container` (colour contrast needs a real browser). */
export async function expectNoA11yViolations(container: Element) {
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  const summary = results.violations.map(
    (violation) =>
      `${violation.id}: ${violation.help} (${violation.nodes.map((node) => node.target.join(" ")).join(", ")})`,
  );
  expect(summary).toEqual([]);
}
