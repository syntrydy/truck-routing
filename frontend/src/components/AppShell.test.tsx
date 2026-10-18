import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { expectNoA11yViolations } from "../test/axe.ts";
import { AppShell } from "./AppShell.tsx";

function setup(overrides: Partial<Parameters<typeof AppShell>[0]> = {}) {
  const onSheetOpenChange = vi.fn();
  const view = render(
    <AppShell
      title="The app"
      panel={<button type="button">a control</button>}
      map={<p>the map</p>}
      slider={<p>the slider</p>}
      sheetOpen
      onSheetOpenChange={onSheetOpenChange}
      {...overrides}
    />,
  );
  return { onSheetOpenChange, user: userEvent.setup(), ...view };
}

describe("AppShell", () => {
  it("lays out the panel, the map and the slider as labelled regions", () => {
    setup();

    expect(screen.getByRole("complementary", { name: "Trip planner" })).toHaveTextContent(
      "a control",
    );
    expect(screen.getByRole("main")).toHaveTextContent("the map");
    expect(screen.getByRole("region", { name: "Forecast" })).toHaveTextContent("the slider");
  });
});

describe("the title", () => {
  it("is the page's one h1, in the panel", () => {
    setup({ title: "Weather-Aware Truck Routing" });

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("Weather-Aware Truck Routing");
    expect(screen.getByRole("complementary")).toContainElement(heading);
  });

  it("stays outside what the sheet folds away, so a closed sheet still has its heading", () => {
    setup({ sheetOpen: false });

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.closest(".shell__panel-content")).toBeNull();
  });
});

describe("the sheet", () => {
  it("has a bar that says it is open and what it controls", () => {
    setup({ sheetOpen: true });

    const bar = screen.getByRole("button", { name: /Trip details/ });
    expect(bar).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(bar.getAttribute("aria-controls") ?? "")).toHaveTextContent(
      "a control",
    );
  });

  it("says it is closed when it is", () => {
    setup({ sheetOpen: false });

    expect(screen.getByRole("button", { name: /Trip details/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("asks to close when open, and to open when closed", async () => {
    const open = setup({ sheetOpen: true });
    await open.user.click(screen.getByRole("button", { name: /Trip details/ }));
    expect(open.onSheetOpenChange).toHaveBeenCalledExactlyOnceWith(false);
    open.unmount();

    const closed = setup({ sheetOpen: false });
    await closed.user.click(screen.getByRole("button", { name: /Trip details/ }));
    expect(closed.onSheetOpenChange).toHaveBeenCalledExactlyOnceWith(true);
  });

  it("works from the keyboard", async () => {
    const { user, onSheetOpenChange } = setup({ sheetOpen: true });

    await user.tab();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");

    expect(onSheetOpenChange).toHaveBeenCalledTimes(2);
  });

  it("shows the summary on the bar when there is one", () => {
    setup({ sheetSummary: "Route A · 17 h 49 min · Trip details", sheetOpen: false });

    expect(screen.getByRole("button", { name: /Route A · 17 h 49 min/ })).toBeInTheDocument();
  });

  it("marks a closed shell for the stylesheet, which hides the panel's content on a phone", () => {
    const { container } = setup({ sheetOpen: false });

    expect(container.firstElementChild).toHaveClass("shell--collapsed");
  });

  it("has no accessibility violations, open or closed", async () => {
    const { container, rerender } = setup({ sheetOpen: true });
    await expectNoA11yViolations(container);

    rerender(
      <AppShell
        title="The app"
        panel={<button type="button">a control</button>}
        map={<p>the map</p>}
        slider={<p>the slider</p>}
        sheetOpen={false}
        onSheetOpenChange={vi.fn()}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
