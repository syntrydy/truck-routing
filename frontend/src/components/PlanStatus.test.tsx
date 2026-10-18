import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type ApiErrorCode } from "../api/errors.ts";
import { expectNoA11yViolations } from "../test/axe.ts";
import { samplePlan } from "../test/plan.ts";
import { PlanStatus } from "./PlanStatus.tsx";

function setup(overrides: Partial<Parameters<typeof PlanStatus>[0]> = {}) {
  const onRetry = vi.fn();
  const view = render(
    <PlanStatus pending={false} error={null} plan={null} onRetry={onRetry} {...overrides} />,
  );
  return { onRetry, user: userEvent.setup(), ...view };
}

const failure = (code: ApiErrorCode, requestId: string | null = "req-9") =>
  new ApiError({ code, message: "server words", status: 500, requestId });

describe("PlanStatus", () => {
  it("says nothing when there is nothing to say", () => {
    const { container } = setup();

    expect(container).toBeEmptyDOMElement();
  });

  it("shows the progress while the plan is worked out", () => {
    setup({ pending: true });

    expect(screen.getByRole("status")).toHaveTextContent("Planning your trip…");
    expect(screen.getByText("Finding routes", { exact: false })).toBeInTheDocument();
  });

  it("announces the plan that arrived, without showing it", () => {
    setup({ plan: samplePlan() });

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Planned 2 routes. Route R1 is recommended.");
    expect(status).toHaveClass("visually-hidden");
  });

  it("says when no route is recommended", () => {
    setup({ plan: { ...samplePlan(), recommended_route_id: null } });

    expect(screen.getByRole("status")).toHaveTextContent("None is recommended.");
  });

  it("says route, not routes, for one", () => {
    const plan = samplePlan();
    setup({ plan: { ...plan, routes: plan.routes.slice(0, 1) } });

    expect(screen.getByRole("status")).toHaveTextContent("Planned 1 route.");
  });
});

describe("an error", () => {
  it("says what happened and what to do, in an alert", () => {
    setup({ error: failure("NO_ROUTE") });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("No drivable route was found between these places");
    expect(alert).toHaveTextContent("Choose places on or near a road");
    expect(alert).not.toHaveTextContent("server words");
  });

  it("gives the reference for support", () => {
    setup({ error: failure("INTERNAL_ERROR") });

    expect(screen.getByRole("alert")).toHaveTextContent("Reference: req-9");
  });

  it("leaves out a missing reference", () => {
    setup({ error: failure("NETWORK", null) });

    expect(screen.getByRole("alert")).not.toHaveTextContent("Reference");
  });

  it("offers to try again when trying again can help, and does so", async () => {
    const { user, onRetry } = setup({ error: failure("UPSTREAM_UNAVAILABLE") });

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it.each(["NO_ROUTE", "TOO_CLOSE", "VALIDATION"] as const)(
    "does not offer to try %s again: the trip has to change first",
    (code) => {
      setup({ error: failure(code) });

      expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    },
  );

  it("says how long to wait after a rate limit", () => {
    setup({
      error: new ApiError({ code: "RATE_LIMITED", message: "x", status: 429, retryAfterS: 60 }),
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Wait 60 seconds, then try again.");
  });

  it("does not show the text of an error it does not know", () => {
    setup({ error: new Error("TypeError: x is undefined") });

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).not.toHaveTextContent("TypeError");
  });

  it("has no accessibility violations", async () => {
    const { container } = setup({ error: failure("UPSTREAM_TIMEOUT") });

    await expectNoA11yViolations(container);
  });
});
