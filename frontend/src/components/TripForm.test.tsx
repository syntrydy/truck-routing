import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiWrapper, stubClient } from "../api/testing.tsx";
import type { ApiClient } from "../api/client.ts";
import type { PlanRequest } from "../api/types.ts";
import { expectNoA11yViolations } from "../test/axe.ts";
import { CHICAGO, DENVER, NOW } from "../test/places.ts";
import { SEARCH_DELAY_MS } from "./PlaceInput.tsx";
import { TripForm } from "./TripForm.tsx";

beforeEach(() => {
  geocode.mockImplementation(defaultGeocode);
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

async function pass(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const defaultGeocode: ApiClient["geocode"] = (query) =>
  Promise.resolve({ results: query.toLowerCase().startsWith("chi") ? [CHICAGO] : [DENVER] });
const geocode = vi.fn<ApiClient["geocode"]>(defaultGeocode);

/** The form with a plan already made for `initial`, as the page holds it. */
function Page({
  initial = null,
  onSubmit,
  onDemo = vi.fn(),
}: {
  initial?: PlanRequest | null;
  onSubmit: (request: PlanRequest) => void;
  onDemo?: (request: PlanRequest) => void;
}) {
  const [planned, setPlanned] = useState(initial);
  return (
    <TripForm
      planned={planned}
      now={() => NOW}
      onSubmit={(request) => {
        setPlanned(request);
        onSubmit(request);
      }}
      onDemo={(request) => {
        setPlanned(request);
        onDemo(request);
      }}
    />
  );
}

function setup(initial: PlanRequest | null = null) {
  const onSubmit = vi.fn();
  const onDemo = vi.fn();
  const user = userEvent.setup({ delay: null });
  const view = render(<Page initial={initial} onSubmit={onSubmit} onDemo={onDemo} />, {
    wrapper: apiWrapper(stubClient({ geocode })),
  });
  return { user, onSubmit, onDemo, ...view };
}

type User = ReturnType<typeof userEvent.setup>;

async function choosePlace(user: User, label: string, typed: string) {
  const field = screen.getByRole("combobox", { name: label });
  await user.clear(field);
  await user.type(field, typed);
  await pass(SEARCH_DELAY_MS);
  await pass(10);
  await user.keyboard("{ArrowDown}{Enter}");
}

async function fillValidTrip(user: User) {
  await choosePlace(user, "From", "chicago");
  await choosePlace(user, "To", "denver");
}

async function clearPlaces(user: User) {
  await user.clear(screen.getByRole("combobox", { name: "From" }));
  await user.clear(screen.getByRole("combobox", { name: "To" }));
}

const submitButton = () => screen.getByRole("button", { name: /plan trip|re-plan/i });

describe("the fields", () => {
  it("has a labelled control for everything the API needs", () => {
    setup();

    expect(screen.getByRole("combobox", { name: "From" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "To" })).toBeInTheDocument();
    expect(screen.getByLabelText("Departure")).toHaveValue("2026-10-18T14:00");
    expect(screen.getByLabelText("Load (lb)")).toHaveValue("42000");
    expect(screen.getByRole("group", { name: "Checkpoint every" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "25 mi" })).toBeChecked();
  });

  it("starts with Chicago to Denver filled in", () => {
    setup();

    expect(screen.getByRole("combobox", { name: "From" })).toHaveValue(CHICAGO.label);
    expect(screen.getByRole("combobox", { name: "To" })).toHaveValue(DENVER.label);
  });

  it("names the time zone the departure is read in", () => {
    setup();

    expect(screen.getByText("Time zone: America/Chicago (UTC-05:00)")).toBeInTheDocument();
  });

  it("changes the checkpoint spacing with the arrow keys", async () => {
    const { user } = setup();

    screen.getByRole("radio", { name: "25 mi" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("radio", { name: "50 mi" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "25 mi" })).not.toBeChecked();
  });

  it("warns about a heavy load without calling it an error", async () => {
    const { user } = setup();
    const load = screen.getByLabelText("Load (lb)");

    await user.clear(load);
    await user.type(load, "90000");

    expect(screen.getByText(/exceeds the usual legal limit/)).toBeInTheDocument();
    expect(load).not.toBeInvalid();
  });
});

describe("validation", () => {
  it("does not complain before the user has touched a field", () => {
    setup();

    expect(screen.queryByText(/Problem:/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Load (lb)")).not.toBeInvalid();
  });

  it("explains a field once the user leaves it", async () => {
    const { user } = setup();
    const load = screen.getByLabelText("Load (lb)");

    await user.clear(load);
    await user.type(load, "heavy");
    expect(screen.queryByText(/whole number of pounds/)).not.toBeInTheDocument();
    await user.tab();

    const message = screen.getByText(/whole number of pounds from 0 to 200,000/);
    expect(load).toBeInvalid();
    expect(load.getAttribute("aria-describedby")).toContain(message.id);
  });

  it("refuses a departure in the past", async () => {
    const { user } = setup();
    const departure = screen.getByLabelText("Departure");

    await user.clear(departure);
    await user.type(departure, "2026-10-18T12:00");
    await user.tab();

    expect(screen.getByText(/at most 15 minutes in the past/)).toBeInTheDocument();
  });

  it("refuses a departure more than a week away", async () => {
    const { user } = setup();
    const departure = screen.getByLabelText("Departure");

    await user.clear(departure);
    await user.type(departure, "2026-10-30T12:00");
    await user.tab();

    expect(screen.getByText(/within the next 7 days/)).toBeInTheDocument();
  });

  it("shows every problem when the form is submitted, and sends nothing", async () => {
    const { user, onSubmit } = setup();
    await clearPlaces(user);

    await user.click(submitButton());

    expect(screen.getByText(/Choose a starting place/)).toBeInTheDocument();
    expect(screen.getByText(/Choose a destination/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("moves focus to the first field with a problem", async () => {
    const { user } = setup();
    await clearPlaces(user);

    await user.click(submitButton());
    await pass(50);

    expect(screen.getByRole("combobox", { name: "From" })).toHaveFocus();
  });

  it("refuses a destination under a mile from the start", async () => {
    const { user } = setup();
    const nextDoor = { ...CHICAGO, label: "Next door", lat: CHICAGO.lat + 0.004 };
    geocode.mockImplementation((query) =>
      Promise.resolve({ results: query === "next door" ? [nextDoor] : [CHICAGO] }),
    );

    await choosePlace(user, "From", "chicago");
    await choosePlace(user, "To", "next door");
    await user.click(submitButton());

    expect(screen.getByText(/at least 1 mile/)).toBeInTheDocument();
  });
});

describe("submitting", () => {
  it("plans the default trip without any input", async () => {
    const { user, onSubmit } = setup();

    await user.click(submitButton());

    expect(onSubmit).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        origin: { lat: CHICAGO.lat, lon: CHICAGO.lon, label: CHICAGO.label },
        destination: { lat: DENVER.lat, lon: DENVER.lon, label: DENVER.label },
      }),
    );
  });

  it("sends the request the API expects", async () => {
    const { user, onSubmit } = setup();
    await fillValidTrip(user);
    await user.click(screen.getByRole("radio", { name: "50 mi" }));

    await user.click(submitButton());

    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      origin: { lat: CHICAGO.lat, lon: CHICAGO.lon, label: CHICAGO.label },
      destination: { lat: DENVER.lat, lon: DENVER.lon, label: DENVER.label },
      departure_at: "2026-10-18T14:00:00-05:00",
      load_lb: 42_000,
      interval_mi: 50,
    });
  });

  it("is not submitted by Enter in a place field that is choosing a place", async () => {
    const { user, onSubmit } = setup();

    await choosePlace(user, "From", "chicago");

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "From" })).toHaveValue(CHICAGO.label);
  });
});

describe("stale inputs", () => {
  async function planned() {
    const context = setup();
    await fillValidTrip(context.user);
    await context.user.click(submitButton());
    return context;
  }

  it("says nothing before a plan is made", () => {
    setup();

    expect(screen.queryByText(/re-plan/)).not.toBeInTheDocument();
    expect(submitButton()).toHaveTextContent("Plan trip");
  });

  it("says nothing right after planning", async () => {
    await planned();

    expect(screen.queryByText("Inputs changed — re-plan")).not.toBeInTheDocument();
    expect(submitButton()).toHaveTextContent("Re-plan");
  });

  it("announces that the plan no longer matches once an input changes", async () => {
    const { user } = await planned();

    await user.click(screen.getByRole("radio", { name: "10 mi" }));

    expect(screen.getByText("Inputs changed — re-plan")).toHaveAttribute("role", "status");
  });

  it("goes away when the input is put back", async () => {
    const { user } = await planned();
    await user.click(screen.getByRole("radio", { name: "10 mi" }));

    await user.click(screen.getByRole("radio", { name: "25 mi" }));

    expect(screen.queryByText("Inputs changed — re-plan")).not.toBeInTheDocument();
  });

  it("appears when a place is un-chosen by editing it", async () => {
    const { user } = await planned();

    await user.type(screen.getByRole("combobox", { name: "To" }), "x");

    expect(screen.getByText("Inputs changed — re-plan")).toBeInTheDocument();
  });
});

describe("accessibility", () => {
  it("has no violations, empty or showing errors", async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const { container } = setup();
    await expectNoA11yViolations(container);

    await clearPlaces(user);
    await user.click(submitButton());
    expect(screen.getByText(/Choose a starting place/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});

describe("the stormy demo", () => {
  const demoButton = () => screen.getByRole("button", { name: "Try the stormy demo" });

  it("comes before the fields of the trip, so that a visitor sees it first", () => {
    setup();

    const fields = screen.getByRole("combobox", { name: "From" });
    expect(
      demoButton().compareDocumentPosition(fields) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("says what it is and that it is not live", () => {
    setup();

    expect(demoButton()).toHaveAccessibleDescription(/recording of a real wind storm/);
    expect(demoButton()).toHaveAccessibleDescription(/Not a live forecast/);
  });

  it("sets the form to the demo trip, leaving now, and keeps the load and the spacing", async () => {
    const { user, onDemo, onSubmit } = setup();
    const load = screen.getByLabelText("Load (lb)");
    await user.clear(load);
    await user.type(load, "36000");
    await user.click(screen.getByRole("radio", { name: "50 mi" }));

    await user.click(demoButton());

    expect(screen.getByRole("combobox", { name: "From" })).toHaveValue(DENVER.label);
    expect(screen.getByRole("combobox", { name: "To" })).toHaveValue(
      "Salt Lake City, Utah, United States",
    );
    expect(screen.getByLabelText("Departure")).toHaveValue("2026-10-18T13:20");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(onDemo).toHaveBeenCalledTimes(1);
    expect(onDemo.mock.calls[0]?.[0]).toMatchObject({
      origin: { label: DENVER.label },
      destination: { label: "Salt Lake City, Utah, United States" },
      load_lb: 36_000,
      interval_mi: 50,
    });
  });

  it("does not start with a load that is not a number, and shows why", async () => {
    const { user, onDemo } = setup();
    const load = screen.getByLabelText("Load (lb)");
    await user.clear(load);
    await user.type(load, "heavy");

    await user.click(demoButton());
    await pass(20);

    expect(onDemo).not.toHaveBeenCalled();
    expect(load).toBeInvalid();
    expect(load).toHaveFocus();
  });
});
