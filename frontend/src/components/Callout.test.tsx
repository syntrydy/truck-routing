import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { expectNoA11yViolations } from "../test/axe.ts";
import { Callout, type CalloutTone } from "./Callout.tsx";

describe("Callout", () => {
  it("has a title and a body, announced with the role it was given", () => {
    render(
      <Callout tone="caution" title="Weather is unavailable" role="status">
        <p>Its risk is shown as unknown.</p>
      </Callout>,
    );

    const callout = screen.getByRole("status");
    expect(callout).toHaveTextContent("Weather is unavailable");
    expect(callout).toHaveTextContent("Its risk is shown as unknown.");
    expect(screen.getByText("Weather is unavailable")).toHaveClass("callout__title");
  });

  it("is an alert when it needs attention at once", () => {
    render(<Callout tone="danger" title="No safe route" role="alert" />);

    expect(screen.getByRole("alert")).toHaveClass("callout--danger");
  });

  it.each(["info", "caution", "danger", "demo"] as CalloutTone[])(
    "marks the %s tone with an icon as well as a colour, hidden from screen readers",
    (tone) => {
      const { container } = render(<Callout tone={tone} title="Title" role="status" />);

      const icon = container.querySelector(".callout__icon svg");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("aria-hidden", "true");
      expect(container.firstElementChild).toHaveClass(`callout--${tone}`);
    },
  );

  it("has no accessibility violations", async () => {
    const { container } = render(
      <Callout tone="info" title="Planning" role="status">
        <p>This usually takes a few seconds.</p>
      </Callout>,
    );

    await expectNoA11yViolations(container);
  });
});
