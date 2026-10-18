import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/errors.ts";
import { apiWrapper, stubClient } from "../api/testing.tsx";
import type { ApiClient } from "../api/client.ts";
import type { Place } from "../api/types.ts";
import { expectNoA11yViolations } from "../test/axe.ts";
import { DENVER, DENVER_IOWA } from "../test/places.ts";
import { PlaceInput, SEARCH_DELAY_MS } from "./PlaceInput.tsx";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

/** Lets timers and the promises behind them run for `ms`. */
async function pass(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** The pause, then the answer: React renders between the two once `act` has ended. */
async function searchSettled() {
  await pass(SEARCH_DELAY_MS);
  await pass(10);
}

function geocodeReturning(...places: Place[]) {
  return vi.fn<ApiClient["geocode"]>(() => Promise.resolve({ results: places }));
}

/** A `PlaceInput` the way a form holds it: the chosen place lives in the parent. */
function Harness({
  onChange,
  initial = null,
}: {
  onChange?: (place: Place | null) => void;
  initial?: Place | null;
}) {
  const [value, setValue] = useState<Place | null>(initial);
  return (
    <PlaceInput
      id="from"
      label="From"
      value={value}
      onChange={(place) => {
        setValue(place);
        onChange?.(place);
      }}
    />
  );
}

function setup(geocode: ApiClient["geocode"], onChange?: (place: Place | null) => void) {
  const user = userEvent.setup({ delay: null }); // no timers of its own: the tests move the clock;
  const view = render(<Harness onChange={onChange} />, {
    wrapper: apiWrapper(stubClient({ geocode })),
  });
  return { user, ...view, input: screen.getByRole("combobox", { name: "From" }) };
}

describe("a place chosen from outside", () => {
  it("shows its name in the box and does not search for it", async () => {
    const geocode = geocodeReturning(DENVER);
    const wrapper = apiWrapper(stubClient({ geocode }));
    const { rerender } = render(
      <PlaceInput id="from" label="From" value={DENVER_IOWA} onChange={() => undefined} />,
      { wrapper },
    );

    rerender(<PlaceInput id="from" label="From" value={DENVER} onChange={() => undefined} />);
    await pass(SEARCH_DELAY_MS + 10);

    expect(screen.getByRole("combobox", { name: "From" })).toHaveValue(DENVER.label);
    expect(geocode).not.toHaveBeenCalled();
  });
});

describe("searching", () => {
  it("waits for a pause in typing before asking", async () => {
    const geocode = geocodeReturning(DENVER);
    const { user, input } = setup(geocode);

    await user.type(input, "denv");
    await pass(SEARCH_DELAY_MS - 1);
    expect(geocode).not.toHaveBeenCalled();

    await pass(1);
    expect(geocode).toHaveBeenCalledTimes(1);
    expect(geocode.mock.calls[0]?.[0]).toBe("denv");
  });

  it("never searches for the label of a place it started with once that is edited", async () => {
    const geocode = geocodeReturning(DENVER);
    const user = userEvent.setup({ delay: null });
    render(<Harness initial={DENVER_IOWA} />, { wrapper: apiWrapper(stubClient({ geocode })) });

    await user.type(screen.getByRole("combobox", { name: "From" }), "x");
    await pass(SEARCH_DELAY_MS + 10);

    expect(geocode).toHaveBeenCalledTimes(1);
    expect(geocode.mock.calls[0]?.[0]).toBe(`${DENVER_IOWA.label}x`);
  });

  it("asks once for what was typed, not for every key", async () => {
    const geocode = geocodeReturning(DENVER);
    const { user, input } = setup(geocode);

    await user.type(input, "denver");
    await pass(SEARCH_DELAY_MS);

    expect(geocode).toHaveBeenCalledTimes(1);
    expect(geocode.mock.calls[0]?.[0]).toBe("denver");
  });

  it("starts again from each key, so a slow typist is still waited for", async () => {
    const geocode = geocodeReturning(DENVER);
    const { user, input } = setup(geocode);

    await user.type(input, "den");
    await pass(SEARCH_DELAY_MS - 100);
    await user.type(input, "v");
    await pass(SEARCH_DELAY_MS - 100);
    expect(geocode).not.toHaveBeenCalled();

    await pass(100);
    expect(geocode.mock.calls[0]?.[0]).toBe("denv");
  });

  it("does not ask for fewer than three characters", async () => {
    const geocode = geocodeReturning(DENVER);
    const { user, input } = setup(geocode);

    await user.type(input, "de");
    await pass(SEARCH_DELAY_MS * 2);

    expect(geocode).not.toHaveBeenCalled();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("tidies spacing before asking", async () => {
    const geocode = geocodeReturning(DENVER);
    const { user, input } = setup(geocode);

    await user.type(input, "  st   louis ");
    await pass(SEARCH_DELAY_MS);

    expect(geocode.mock.calls[0]?.[0]).toBe("st louis");
  });

  it("says it is searching until the answer is in", async () => {
    let answer: (value: { results: Place[] }) => void = () => undefined;
    const geocode = vi.fn<ApiClient["geocode"]>(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    );
    const { user, input } = setup(geocode);

    await user.type(input, "denver");
    expect(screen.getByRole("status")).toHaveTextContent("Searching");
    await pass(SEARCH_DELAY_MS);
    expect(screen.getByRole("status")).toHaveTextContent("Searching");

    await act(async () => {
      answer({ results: [DENVER] });
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByRole("status")).toHaveTextContent("1 place found");
  });
});

describe("the list", () => {
  async function listed() {
    const context = setup(geocodeReturning(DENVER, DENVER_IOWA));
    await context.user.type(context.input, "denver");
    await searchSettled();
    return context;
  }

  it("shows the places with what kind each is", async () => {
    await listed();

    const options = screen.getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      "Denver, Colorado, United States city",
      "Denver, Iowa, United States city",
    ]);
    expect(screen.getByRole("status")).toHaveTextContent("2 places found");
  });

  it("is a combobox wired to its list", async () => {
    const { input } = await listed();

    const list = screen.getByRole("listbox", { name: "From suggestions" });
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(input).toHaveAttribute("aria-controls", list.id);
    expect(input).toHaveAttribute("aria-autocomplete", "list");
    expect(input).not.toHaveAttribute("aria-activedescendant");
  });

  it("moves through the places with the arrow keys, wrapping round", async () => {
    const { user, input } = await listed();
    const [first, second] = screen.getAllByRole("option");

    await user.keyboard("{ArrowDown}");
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(input).toHaveAttribute("aria-activedescendant", first?.id);

    await user.keyboard("{ArrowDown}");
    expect(second).toHaveAttribute("aria-selected", "true");
    expect(first).toHaveAttribute("aria-selected", "false");

    await user.keyboard("{ArrowDown}");
    expect(first).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowUp}");
    expect(second).toHaveAttribute("aria-selected", "true");
  });

  it("keeps focus in the field while moving through the list", async () => {
    const { user, input } = await listed();

    await user.keyboard("{ArrowDown}{ArrowDown}");

    expect(input).toHaveFocus();
  });

  it("chooses the highlighted place with Enter", async () => {
    const onChange = vi.fn();
    const geocode = geocodeReturning(DENVER, DENVER_IOWA);
    const { user, input } = setup(geocode, onChange);
    await user.type(input, "denver");
    await searchSettled();

    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledExactlyOnceWith(DENVER_IOWA);
    expect(input).toHaveValue(DENVER_IOWA.label);
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("does nothing on Enter when no place is highlighted", async () => {
    const onChange = vi.fn();
    const { user, input } = setup(geocodeReturning(DENVER), onChange);
    await user.type(input, "denver");
    await searchSettled();

    await user.keyboard("{Enter}");

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("listbox")).toBeVisible();
  });

  it("chooses a place that is clicked", async () => {
    const onChange = vi.fn();
    const { user, input } = setup(geocodeReturning(DENVER, DENVER_IOWA), onChange);
    await user.type(input, "denver");
    await searchSettled();

    await user.click(screen.getByRole("option", { name: /Iowa/ }));

    expect(onChange).toHaveBeenCalledExactlyOnceWith(DENVER_IOWA);
    expect(input).toHaveValue(DENVER_IOWA.label);
    expect(input).toHaveFocus();
  });

  it("closes with Escape and opens again with an arrow key", async () => {
    const { user, input } = await listed();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
    expect(input).toHaveAttribute("aria-expanded", "false");

    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("closes when the field is left", async () => {
    const { user } = await listed();

    await user.tab();

    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("is clear again, and searches again, once the chosen text is edited", async () => {
    const onChange = vi.fn();
    const geocode = geocodeReturning(DENVER);
    const { user, input } = setup(geocode, onChange);
    await user.type(input, "denver");
    await searchSettled();
    await user.keyboard("{ArrowDown}{Enter}");
    onChange.mockClear();

    await user.type(input, "x");

    expect(onChange).toHaveBeenCalledExactlyOnceWith(null);
    await searchSettled();
    expect(geocode).toHaveBeenLastCalledWith(`${DENVER.label}x`, expect.any(AbortSignal));
  });

  it("does not search again for the text of a place that was chosen", async () => {
    const geocode = geocodeReturning(DENVER);
    const { user, input } = setup(geocode);
    await user.type(input, "denver");
    await searchSettled();
    await user.keyboard("{ArrowDown}{Enter}");
    await pass(SEARCH_DELAY_MS * 2);

    expect(geocode).toHaveBeenCalledTimes(1);
  });
});

describe("when there is nothing to show", () => {
  it("says so when no place matches", async () => {
    const { user, input } = setup(geocodeReturning());

    await user.type(input, "qzxwvb");
    await searchSettled();

    expect(screen.getByRole("status")).toHaveTextContent("No places found");
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("says so when the search fails, without losing what was typed", async () => {
    const geocode = vi.fn<ApiClient["geocode"]>(() =>
      Promise.reject(new ApiError({ code: "UPSTREAM_UNAVAILABLE", message: "down", status: 503 })),
    );
    const { user, input } = setup(geocode);

    await user.type(input, "denver");
    await searchSettled();

    expect(screen.getByRole("status")).toHaveTextContent("unavailable");
    expect(input).toHaveValue("denver");
  });
});

describe("accessibility", () => {
  it("has no violations, closed or open", async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const { container } = render(<Harness />, {
      wrapper: apiWrapper(stubClient({ geocode: geocodeReturning(DENVER) })),
    });
    await expectNoA11yViolations(container);

    await user.type(screen.getByRole("combobox"), "denver");
    await screen.findByRole("option", {}, { timeout: 2000 });
    await expectNoA11yViolations(container);
  });
});
