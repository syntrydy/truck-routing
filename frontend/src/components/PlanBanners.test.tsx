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
    expect(alert).toHaveTextContent("No safe route");
    expect(alert).toHaveTextContent("still ranked");
    expect(screen.queryByText(/Weather is unavailable/)).not.toBeInTheDocument();
  });

  it("says that unknown weather is unknown, not low", () => {
    render(<PlanBanners plan={planWith({ banner: "WEATHER_UNAVAILABLE" })} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Weather is unavailable for some places");
    expect(status).toHaveTextContent("unknown, not as low");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says the demo is a recording, and says nothing of the kind for a live plan", () => {
    const demo = planWith({ meta: { ...samplePlan().meta, weather_source: "demo" } });
    const { rerender } = render(<PlanBanners plan={demo} />);

    expect(screen.getByRole("status")).toHaveTextContent("Demo: a recording, not a live forecast");
    expect(screen.getByRole("status")).toHaveTextContent("17 January 2024");

    rerender(<PlanBanners plan={planWith({ banner: null, notes: [] })} />);

    expect(screen.queryByText(/Demo:/)).not.toBeInTheDocument();
  });

  it("does not repeat the weather banner as a note", () => {
    const repeated = "Weather is unavailable for 3 locations; their risk is shown as unknown";
    render(
      <PlanBanners
        plan={planWith({
          banner: "WEATHER_UNAVAILABLE",
          notes: ["ETAs assume continuous driving at ≤ 65 mph", repeated],
        })}
      />,
    );

    expect(screen.getByText("Weather is unavailable for some places")).toBeInTheDocument();
    expect(screen.queryByText(repeated)).not.toBeInTheDocument();
    expect(screen.getByText("ETAs assume continuous driving at ≤ 65 mph")).toBeInTheDocument();
  });

  it("keeps the missing-weather note when another banner is shown", () => {
    const missing = "Weather is unavailable for 1 location; their risk is shown as unknown";
    render(<PlanBanners plan={planWith({ banner: "NO_SAFE_ROUTE", notes: [missing] })} />);

    expect(screen.getByText(missing)).toBeInTheDocument();
  });

  it("does not leave an empty list when the only note was the repeat", () => {
    render(
      <PlanBanners
        plan={planWith({
          banner: "WEATHER_UNAVAILABLE",
          notes: ["Weather is unavailable for 2 locations; their risk is shown as unknown"],
        })}
      />,
    );

    expect(screen.queryByRole("list")).not.toBeInTheDocument();
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
