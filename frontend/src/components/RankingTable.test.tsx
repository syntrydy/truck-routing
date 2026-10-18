import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PlanResponse } from "../api/types.ts";
import { expectNoA11yViolations } from "../test/axe.ts";
import { samplePlan } from "../test/plan.ts";
import { formatCriterionValue, RankingTable } from "./RankingTable.tsx";

function planWith(changes: Partial<PlanResponse> = {}): PlanResponse {
  return { ...samplePlan(), ...changes };
}

describe("RankingTable", () => {
  it("is titled as the question the recommendation answers", () => {
    render(<RankingTable plan={planWith()} />);

    expect(screen.getByText("Why this route?")).toBeInTheDocument();
  });

  it("is a table with a column for each route, best first, and the recommended one named", () => {
    render(<RankingTable plan={planWith()} />);

    const headers = screen.getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual(["Route R1 (recommended)", "Route R2"]);
  });

  it("lists the criteria in ranking order, numbered", () => {
    render(<RankingTable plan={planWith()} />);

    const rows = screen.getAllByRole("rowheader").map((header) => header.textContent);
    expect(rows).toEqual([
      "1. No Travel miles",
      "2. Severe miles",
      "3. High-risk miles",
      "4. Average risk decided here",
      "5. Travel time",
    ]);
  });

  it("shows each route's value in words and units", () => {
    render(<RankingTable plan={planWith()} />);

    const risk = screen.getByRole("row", { name: /Average risk/ });
    expect(
      within(risk)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["0.15 ✓ (best)", "0.27"]);
    const time = screen.getByRole("row", { name: /Travel time/ });
    expect(within(time).getAllByRole("cell")[0]).toHaveTextContent("9 h 57 min");
  });

  it("marks the deciding row once, in words, not by colour alone", () => {
    render(<RankingTable plan={planWith()} />);

    expect(screen.getAllByText("decided here")).toHaveLength(1);
    expect(screen.getByRole("row", { name: /decided here/ })).toHaveTextContent("Average risk");
  });

  it("marks no best value in a row where every route is equally good", () => {
    render(<RankingTable plan={planWith()} />);

    const severe = screen.getByRole("row", { name: /Severe miles/ });
    expect(
      within(severe)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["0 mi", "0 mi"]);
  });

  it("says unknown for an average risk that is unknown, never zero", () => {
    const plan = planWith();
    const risk = plan.ranking.criteria.find((criterion) => criterion.id === "AVG_RISK");
    if (risk === undefined) {
      throw new Error("the sample ranking has an average risk");
    }
    risk.values = [
      { route_id: "r1", value: 0.15, best: true },
      { route_id: "r2", value: null, best: false },
    ];

    render(<RankingTable plan={plan} />);

    expect(screen.getByRole("row", { name: /Average risk/ })).toHaveTextContent("unknown");
  });

  it("is titled as a ranking when no route is safe, since the ranking still exists", () => {
    render(
      <RankingTable plan={planWith({ recommended_route_id: null, banner: "NO_SAFE_ROUTE" })} />,
    );

    expect(screen.getByText("How the routes were ranked")).toBeInTheDocument();
    expect(screen.queryByText("(recommended)")).not.toBeInTheDocument();
  });

  it("is not drawn for a single route, which has nothing to compare", () => {
    const plan = planWith();
    for (const criterion of plan.ranking.criteria) {
      criterion.values = criterion.values.slice(0, 1);
    }

    const { container } = render(<RankingTable plan={plan} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<RankingTable plan={planWith()} />);

    await expectNoA11yViolations(container);
  });
});

describe("formatCriterionValue", () => {
  it.each([
    ["mi", 75, "75 mi"],
    ["mi", 0, "0 mi"],
    ["risk", 0.15, "0.15"],
    ["risk", 1, "1.00"],
    ["risk", null, "unknown"],
    ["s", 35_820, "9 h 57 min"],
  ] as const)("writes %s %s as %s", (unit, value, text) => {
    expect(formatCriterionValue(unit, value)).toBe(text);
  });
});
