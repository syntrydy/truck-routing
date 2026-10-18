import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoA11yViolations } from "../test/axe.ts";
import { currentStep, PlanProgress, STEPS } from "./PlanProgress.tsx";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

const stepStates = () =>
  within(screen.getByRole("list"))
    .getAllByRole("listitem")
    .map((item) => item.textContent);

describe("currentStep", () => {
  it.each([
    [0, 0],
    [3, 0],
    [4, 1],
    [13, 1],
    [14, 2],
    [600, 2],
  ])("is step %d at %d seconds", (seconds, step) => {
    expect(currentStep(seconds)).toBe(step);
  });

  it("has three steps, the last without an end", () => {
    expect(STEPS.map((step) => step.label)).toEqual([
      "Finding routes",
      "Checking the weather along each route",
      "Building the forecast",
    ]);
    expect(STEPS[2].untilS).toBe(Infinity);
  });
});

describe("PlanProgress", () => {
  it("says it is working, and how long that usually takes", () => {
    render(<PlanProgress />);

    expect(screen.getByRole("status")).toHaveTextContent("Planning your trip…");
    expect(screen.getByText(/usually takes 5 to 15 seconds/)).toBeInTheDocument();
    expect(screen.getByText(/steps are an estimate/)).toBeInTheDocument();
  });

  it("starts on the first step, and says the state of each in words", () => {
    render(<PlanProgress />);

    expect(stepStates()).toEqual([
      expect.stringContaining("Finding routes (in progress)"),
      expect.stringContaining("Checking the weather along each route (waiting)"),
      expect.stringContaining("Building the forecast (waiting)"),
    ]);
  });

  it("moves on as time passes, marking finished steps done", () => {
    render(<PlanProgress />);

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(stepStates()).toEqual([
      expect.stringContaining("Finding routes (done)"),
      expect.stringContaining("(in progress)"),
      expect.stringContaining("(waiting)"),
    ]);

    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(stepStates()).toEqual([
      expect.stringContaining("(done)"),
      expect.stringContaining("(done)"),
      expect.stringContaining("Building the forecast (in progress)"),
    ]);
  });

  it("stays on the last step however long it takes", () => {
    render(<PlanProgress />);

    act(() => {
      vi.advanceTimersByTime(120_000);
    });

    expect(stepStates()[2]).toContain("(in progress)");
  });

  it("has no accessibility violations", async () => {
    vi.useRealTimers();
    const { container } = render(<PlanProgress />);

    await expectNoA11yViolations(container);
  });
});
