import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { HeatmapVariable } from "../lib/heatmap.ts";
import { expectNoA11yViolations } from "../test/axe.ts";
import { ForecastSlider } from "./ForecastSlider.tsx";

const START = "2026-10-18T19:00:00Z"; // 2:00 PM in the test time zone

function setup(overrides: Partial<Parameters<typeof ForecastSlider>[0]> = {}) {
  const handlers = {
    onHourChange: vi.fn(),
    onTogglePlay: vi.fn(),
    onVariableChange: vi.fn(),
  };
  const view = render(
    <ForecastSlider
      startIso={START}
      hour={0}
      maxHour={48}
      playing={false}
      variable="risk"
      {...handlers}
      {...overrides}
    />,
  );
  return { ...handlers, user: userEvent.setup(), ...view };
}

const slider = () => screen.getByRole("slider", { name: "Forecast hour" });

describe("the slider", () => {
  it("covers the 49 hours", () => {
    setup();

    expect(slider()).toHaveAttribute("min", "0");
    expect(slider()).toHaveAttribute("max", "48");
    expect(slider()).toHaveAttribute("step", "1");
  });

  it("says the time in words, with the local zone and the hours ahead", () => {
    setup({ hour: 3 });

    expect(slider()).toHaveAttribute("aria-valuetext", "Sun, 5:00 PM CDT (UTC-05:00), +3 h");
    expect(screen.getByText("Sun, 5:00 PM CDT (UTC-05:00), +3 h")).toBeInTheDocument();
  });

  it("says when it is the time of departure", () => {
    setup({ hour: 0 });

    expect(slider()).toHaveAttribute("aria-valuetext", expect.stringContaining("at departure"));
  });

  it("shows the day change", () => {
    setup({ hour: 12 });

    expect(slider()).toHaveAttribute("aria-valuetext", expect.stringContaining("Mon, 2:00 AM"));
  });

  // Arrow keys, Home, End and Page Up/Down are the browser's own behaviour for a range input
  // (jsdom does not implement them); they were checked by hand in a real browser.
  it("reports the hour when the slider is moved", () => {
    const { onHourChange } = setup({ hour: 10 });

    fireEvent.change(slider(), { target: { value: "11" } });
    expect(onHourChange).toHaveBeenLastCalledWith(11);
    fireEvent.change(slider(), { target: { value: "48" } });
    expect(onHourChange).toHaveBeenLastCalledWith(48);
  });

  it("can be reached and operated from the keyboard", async () => {
    const { user } = setup();

    await user.tab(); // the play button
    await user.tab();

    expect(slider()).toHaveFocus();
  });

  it("follows the hour it is given", () => {
    const { rerender } = setup({ hour: 4 });
    expect(slider()).toHaveValue("4");

    rerender(
      <ForecastSlider
        startIso={START}
        hour={30}
        maxHour={48}
        playing={false}
        variable="risk"
        onHourChange={vi.fn()}
        onTogglePlay={vi.fn()}
        onVariableChange={vi.fn()}
      />,
    );

    expect(slider()).toHaveValue("30");
  });
});

describe("playing", () => {
  it("offers to play, then to pause", () => {
    const { rerender } = setup({ playing: false });
    expect(screen.getByRole("button", { name: /Play/ })).toHaveAttribute("aria-pressed", "false");

    rerender(
      <ForecastSlider
        startIso={START}
        hour={0}
        maxHour={48}
        playing
        variable="risk"
        onHourChange={vi.fn()}
        onTogglePlay={vi.fn()}
        onVariableChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /Pause/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("asks to toggle by click, Enter and Space", async () => {
    const { user, onTogglePlay } = setup();
    const button = screen.getByRole("button", { name: /Play/ });

    await user.click(button);
    button.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");

    expect(onTogglePlay).toHaveBeenCalledTimes(3);
  });
});

describe("the variable", () => {
  it("offers risk, wind, rain and snow, with the current one chosen", () => {
    setup({ variable: "wind" });

    const group = screen.getByRole("group", { name: "Map shows" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => radio.getAttribute("value")),
    ).toEqual(["risk", "wind", "rain", "snow"]);
    expect(within(group).getByRole("radio", { name: "Wind" })).toBeChecked();
    expect(within(group).getByRole("radio", { name: "Risk" })).not.toBeChecked();
  });

  it("reports the choice, by mouse and by arrow key", async () => {
    const { user, onVariableChange } = setup();

    await user.click(screen.getByRole("radio", { name: "Rain" }));
    expect(onVariableChange).toHaveBeenLastCalledWith("rain");

    screen.getByRole("radio", { name: "Risk" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(onVariableChange).toHaveBeenLastCalledWith("wind");
  });

  it("explains the colours of the chosen variable in words", () => {
    setup({ variable: "wind" });

    const legend = screen.getByRole("list", { name: "What the colours mean" });
    expect(within(legend).getByText("Moderate: 25 to 35 mph")).toBeInTheDocument();
    expect(within(legend).getByText("Unknown: no forecast")).toBeInTheDocument();
  });

  it("changes the explanation with the variable", () => {
    function Page() {
      const [variable, setVariable] = useState<HeatmapVariable>("risk");
      return (
        <ForecastSlider
          startIso={START}
          hour={0}
          maxHour={48}
          playing={false}
          variable={variable}
          onHourChange={vi.fn()}
          onTogglePlay={vi.fn()}
          onVariableChange={setVariable}
        />
      );
    }
    render(<Page />);
    expect(screen.queryByText(/mph/)).not.toBeInTheDocument();

    return userEvent
      .setup()
      .click(screen.getByRole("radio", { name: "Wind" }))
      .then(() => {
        expect(screen.getByText("Severe: 45 to 55 mph")).toBeInTheDocument();
      });
  });
});

describe("accessibility", () => {
  it("has no violations, paused or playing", async () => {
    const { container, rerender } = setup({ hour: 7 });
    await expectNoA11yViolations(container);

    rerender(
      <ForecastSlider
        startIso={START}
        hour={7}
        maxHour={48}
        playing
        variable="snow"
        onHourChange={vi.fn()}
        onTogglePlay={vi.fn()}
        onVariableChange={vi.fn()}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
