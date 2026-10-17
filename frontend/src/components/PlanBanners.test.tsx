import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { samplePlan } from "../test/plan.ts";
import { PlanBanners } from "./PlanBanners.tsx";

const planWith = (changes: Partial<ReturnType<typeof samplePlan>>) => ({
  ...samplePlan(),
  ...changes,
});

describe("PlanBanners", () => {
  it("shows nothing for a plan with nothing to warn about", () => {
    const { container } = render(<PlanBanners plan={planWith({ banner: null, notes: [] })} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(container.textContent).toBe("");
  });

  it("warns urgently when there is no safe route", () => {
    render(<PlanBanners plan={planWith({ banner: "NO_SAFE_ROUTE" })} />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("No safe route.");
    expect(alert).toHaveTextContent("still ranked");
    expect(screen.queryByText(/Weather is unavailable/)).not.toBeInTheDocument();
  });

  it("says that unknown weather is unknown, not low", () => {
    render(<PlanBanners plan={planWith({ banner: "WEATHER_UNAVAILABLE" })} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Weather is unavailable for some places.");
    expect(status).toHaveTextContent("unknown, not as low");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lists the notes of the plan", () => {
    render(
      <PlanBanners
        plan={planWith({
          notes: [
            "ETAs assume continuous driving at ≤ 65 mph",
            "A load above 80,000 lb exceeds the usual legal limit",
          ],
        })}
      />,
    );

    const notes = screen.getByRole("list", { name: "Notes about this plan" });
    expect(notes.textContent).toContain("ETAs assume continuous driving");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("shows a banner and notes together", () => {
    render(<PlanBanners plan={planWith({ banner: "WEATHER_UNAVAILABLE", notes: ["One note"] })} />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("One note")).toBeInTheDocument();
  });
});
