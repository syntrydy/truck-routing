import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { PlanResponse } from "../api/types.ts";
import { expectNoA11yViolations } from "../test/axe.ts";
import { samplePlan } from "../test/plan.ts";
import { RouteCards } from "./RouteCards.tsx";

function plan(): PlanResponse {
  const base = samplePlan();
  const [first, second] = base.routes;
  if (first === undefined || second === undefined) {
    throw new Error("the sample plan has two routes");
  }
  return {
    ...base,
    routes: [
      {
        ...first,
        distance_mi: 1003.1,
        duration_s: 17 * 3600 + 5 * 60,
        summary: {
          ...first.summary,
          miles_by_level: { LOW: 850, MODERATE: 120 },
          unknown_miles: 33,
          worst_level: "MODERATE" as const,
        },
      },
      {
        ...second,
        distance_mi: 1067.4,
        duration_s: 18 * 3600,
        summary: {
          ...second.summary,
          miles_by_level: { LOW: 900, HIGH: 100 },
          worst_level: "HIGH" as const,
          low_confidence: true,
        },
      },
    ],
  };
}

function setup(overrides: { selectedId?: string | null; hoveredId?: string | null } = {}) {
  const onSelect = vi.fn();
  const onHover = vi.fn();
  const view = render(
    <RouteCards
      plan={plan()}
      selectedId={overrides.selectedId ?? "r1"}
      hoveredId={overrides.hoveredId ?? null}
      onSelect={onSelect}
      onHover={onHover}
    />,
  );
  return { onSelect, onHover, user: userEvent.setup(), ...view };
}

const card = (name: string) =>
  screen.getByRole("heading", { name: new RegExp(name) }).closest("li") as HTMLElement;

describe("the cards", () => {
  it("lists the routes in order, each under a heading", () => {
    setup();

    expect(screen.getByRole("heading", { level: 2, name: "Routes" })).toBeInTheDocument();
    expect(
      screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent),
    ).toEqual([expect.stringContaining("Route R1"), expect.stringContaining("Route R2")]);
  });

  it("says the rank in words for screen readers", () => {
    setup();

    expect(within(card("Route R2")).getByText("Rank")).toHaveClass("visually-hidden");
    expect(card("Route R2")).toHaveTextContent("Rank 2");
  });

  it("shows how long, how far and how bad it gets", () => {
    setup();

    expect(card("Route R1")).toHaveTextContent("17 h 5 min · 1,003 mi · Worst: Moderate");
    expect(card("Route R2")).toHaveTextContent("18 h · 1,067 mi · Worst: High");
  });

  it("recommends one route and gives the reason on it alone", () => {
    setup();

    expect(within(card("Route R1")).getByText("Recommended")).toBeInTheDocument();
    expect(within(card("Route R1")).getByText("Lowest weather risk")).toBeInTheDocument();
    expect(within(card("Route R2")).queryByText("Recommended")).not.toBeInTheDocument();
    expect(screen.getAllByText("Lowest weather risk")).toHaveLength(1);
  });

  it("recommends nothing when the plan has no recommendation", () => {
    const noSafe = { ...plan(), recommended_route_id: null, recommendation_reason: null };
    render(
      <RouteCards
        plan={noSafe}
        selectedId="r1"
        hoveredId={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
      />,
    );

    expect(screen.queryByText("Recommended")).not.toBeInTheDocument();
  });

  it("warns that a route's weather is incomplete", () => {
    setup();

    expect(within(card("Route R2")).getByText(/Low confidence/)).toBeInTheDocument();
    expect(within(card("Route R1")).queryByText(/Low confidence/)).not.toBeInTheDocument();
  });

  it("shows nothing for a plan without routes", () => {
    const { container } = render(
      <RouteCards
        plan={{ ...plan(), routes: [] }}
        selectedId={null}
        hoveredId={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("the risk bar", () => {
  it("says the miles by level in words", () => {
    setup();

    const legend = within(card("Route R1")).getByRole("list", { name: "Miles by risk level" });
    expect(
      within(legend)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Low 850 mi", "Moderate 120 mi", "Unknown 33 mi"]);
  });

  it("leaves out levels the route does not have", () => {
    setup();

    expect(card("Route R2")).not.toHaveTextContent("Unknown");
    expect(card("Route R2")).toHaveTextContent("High 100 mi");
  });

  it("hides the coloured bar from screen readers, since the words say it", () => {
    setup();

    const track = card("Route R1").querySelector(".risk-bar__track");
    expect(track).toHaveAttribute("aria-hidden", "true");
    expect(track?.children).toHaveLength(3);
  });

  it("sizes the segments by their share of the route", () => {
    setup();

    const widths = [...(card("Route R2").querySelector(".risk-bar__track")?.children ?? [])].map(
      (segment) => (segment as HTMLElement).style.width,
    );
    expect(widths).toEqual(["90%", "10%"]);
  });
});

describe("choosing a route", () => {
  it("marks the selected route, in words as well as in style", () => {
    setup({ selectedId: "r2" });

    expect(within(card("Route R2")).getByRole("button")).toHaveAttribute("aria-pressed", "true");
    expect(within(card("Route R1")).getByRole("button")).toHaveAttribute("aria-pressed", "false");
    expect(within(card("Route R2")).getByText("Shown on map")).toBeInTheDocument();
    expect(card("Route R2")).toHaveClass("route-card--selected");
  });

  it("selects a route with a click", async () => {
    const { user, onSelect } = setup();

    await user.click(screen.getByRole("button", { name: "Route R2" }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith("r2");
  });

  it("selects a route with the keyboard", async () => {
    const { user, onSelect } = setup();

    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Route R2" })).toHaveFocus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");

    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(onSelect).toHaveBeenCalledWith("r2");
  });

  it("highlights a route as the pointer or focus arrives, and clears it on leaving", async () => {
    const { user, onHover } = setup();
    const button = screen.getByRole("button", { name: "Route R2" });

    await user.hover(button);
    expect(onHover).toHaveBeenLastCalledWith("r2");
    await user.unhover(button);
    expect(onHover).toHaveBeenLastCalledWith(null);

    await user.tab();
    await user.tab();
    expect(onHover).toHaveBeenLastCalledWith("r2");
    await user.tab();
    expect(onHover).toHaveBeenLastCalledWith(null);
  });

  it("shows the route the pointer is over on the map", () => {
    setup({ hoveredId: "r2" });

    expect(card("Route R2")).toHaveClass("route-card--hovered");
    expect(card("Route R1")).not.toHaveClass("route-card--hovered");
  });

  it("follows the choice when the page holds the selection", async () => {
    function Page() {
      const [selected, setSelected] = useState("r1");
      return (
        <RouteCards
          plan={plan()}
          selectedId={selected}
          hoveredId={null}
          onSelect={setSelected}
          onHover={vi.fn()}
        />
      );
    }
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getByRole("button", { name: "Route R2" }));

    expect(card("Route R2")).toHaveClass("route-card--selected");
    expect(card("Route R1")).not.toHaveClass("route-card--selected");
  });
});

describe("accessibility", () => {
  it("has no violations", async () => {
    const { container } = setup({ selectedId: "r1" });

    await expectNoA11yViolations(container);
  });
});
