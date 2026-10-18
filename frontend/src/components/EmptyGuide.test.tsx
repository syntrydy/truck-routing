import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { expectNoA11yViolations } from "../test/axe.ts";
import { EmptyGuide } from "./EmptyGuide.tsx";

describe("EmptyGuide", () => {
  it("lists what a plan gives, as a list", () => {
    render(<EmptyGuide />);

    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual([
      "Up to three routes, ranked by weather risk",
      "The weather at each checkpoint, when the truck gets there",
      "A forecast for the next 48 hours along the way",
    ]);
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<EmptyGuide />);

    await expectNoA11yViolations(container);
  });
});
