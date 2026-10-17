import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiError } from "../api/errors.ts";
import { PlanStatus } from "./PlanStatus.tsx";

describe("PlanStatus", () => {
  it("says nothing when there is nothing to say", () => {
    const { container } = render(<PlanStatus pending={false} error={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("says the trip is being planned", () => {
    render(<PlanStatus pending error={null} />);

    expect(screen.getByRole("status")).toHaveTextContent("Planning your trip");
  });

  it("shows the API's message and the reference for support", () => {
    const error = new ApiError({
      code: "NO_ROUTE",
      message: "No drivable route was found between these places",
      status: 422,
      requestId: "req-9",
    });

    render(<PlanStatus pending={false} error={error} />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No drivable route was found between these places (reference req-9)",
    );
  });

  it("leaves out an empty reference", () => {
    const error = new ApiError({
      code: "NETWORK",
      message: "The server could not be reached",
      status: 0,
    });

    render(<PlanStatus pending={false} error={error} />);

    expect(screen.getByRole("alert")).not.toHaveTextContent("reference");
  });

  it("does not show the text of an error it does not know", () => {
    render(<PlanStatus pending={false} error={new Error("TypeError: x is undefined")} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("TypeError");
  });
});
