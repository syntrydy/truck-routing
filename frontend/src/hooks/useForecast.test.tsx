import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { samplePlan } from "../test/plan.ts";
import { PLAY_STEP_MS, useForecast } from "./useForecast.ts";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

const plan = samplePlan();

function setup(initial = plan) {
  return renderHook(({ current }) => useForecast(current), { initialProps: { current: initial } });
}

const advance = (ms: number) => {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
};

describe("useForecast", () => {
  it("starts at the first hour, paused, showing risk", () => {
    const { result } = setup();

    expect(result.current).toMatchObject({
      hour: 0,
      maxHour: 48,
      playing: false,
      variable: "risk",
    });
    expect(result.current.frames).toHaveLength(49);
  });

  it("has nothing to show without a plan", () => {
    const { result } = renderHook(() => useForecast(null));

    expect(result.current.frames).toBeNull();
    expect(result.current.maxHour).toBe(0);
  });

  it("moves to the hour it is given, whole and within range", () => {
    const { result } = setup();

    act(() => {
      result.current.setHour(12.4);
    });
    expect(result.current.hour).toBe(12);
    act(() => {
      result.current.setHour(500);
    });
    expect(result.current.hour).toBe(48);
    act(() => {
      result.current.setHour(-3);
    });
    expect(result.current.hour).toBe(0);
  });

  it("builds the frames once, and again only for another variable", () => {
    const { result } = setup();
    const first = result.current.frames;

    act(() => {
      result.current.setHour(5);
    });
    expect(result.current.frames).toBe(first);

    act(() => {
      result.current.setVariable("wind");
    });
    expect(result.current.frames).not.toBe(first);
    expect(result.current.variable).toBe("wind");
  });
});

describe("playing", () => {
  it("steps one hour every 400 ms", () => {
    const { result } = setup();

    act(() => {
      result.current.togglePlay();
    });
    expect(result.current.playing).toBe(true);
    advance(PLAY_STEP_MS - 1);
    expect(result.current.hour).toBe(0);
    advance(1);
    expect(result.current.hour).toBe(1);
    advance(PLAY_STEP_MS * 3);
    expect(result.current.hour).toBe(4);
  });

  it("is 400 ms as the SPEC says", () => {
    expect(PLAY_STEP_MS).toBe(400);
  });

  it("stops at the last hour", () => {
    const { result } = setup();
    act(() => {
      result.current.setHour(46);
      result.current.togglePlay();
    });

    advance(PLAY_STEP_MS * 5);

    expect(result.current).toMatchObject({ hour: 48, playing: false });
    advance(PLAY_STEP_MS * 5);
    expect(result.current.hour).toBe(48);
  });

  it("pauses where it is", () => {
    const { result } = setup();
    act(() => {
      result.current.togglePlay();
    });
    advance(PLAY_STEP_MS * 2);

    act(() => {
      result.current.togglePlay();
    });
    advance(PLAY_STEP_MS * 5);

    expect(result.current).toMatchObject({ hour: 2, playing: false });
  });

  it("starts again from the beginning when played at the end", () => {
    const { result } = setup();
    act(() => {
      result.current.setHour(48);
    });

    act(() => {
      result.current.togglePlay();
    });

    expect(result.current).toMatchObject({ hour: 0, playing: true });
  });

  it("stops when the slider is dragged", () => {
    const { result } = setup();
    act(() => {
      result.current.togglePlay();
    });
    advance(PLAY_STEP_MS);

    act(() => {
      result.current.setHour(20);
    });
    advance(PLAY_STEP_MS * 3);

    expect(result.current).toMatchObject({ hour: 20, playing: false });
  });

  it("keeps playing when only the variable changes", () => {
    const { result } = setup();
    act(() => {
      result.current.togglePlay();
    });
    advance(PLAY_STEP_MS);

    act(() => {
      result.current.setVariable("rain");
    });
    advance(PLAY_STEP_MS);

    expect(result.current).toMatchObject({ hour: 2, playing: true, variable: "rain" });
  });

  it("does not play a plan with a single frame", () => {
    const { result } = setup({
      ...plan,
      heatmap: { ...plan.heatmap, frames: plan.heatmap.frames.slice(0, 1) },
    });

    act(() => {
      result.current.togglePlay();
    });

    expect(result.current.playing).toBe(false);
  });

  it("cleans up its timer when it goes away", () => {
    const { result, unmount } = setup();
    act(() => {
      result.current.togglePlay();
    });

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("a new plan", () => {
  it("starts again from the first hour and stops playing, keeping the variable", () => {
    const { result, rerender } = setup();
    act(() => {
      result.current.setVariable("snow");
      result.current.setHour(30);
      result.current.togglePlay();
    });
    advance(PLAY_STEP_MS);
    expect(result.current.hour).toBe(31);

    rerender({ current: samplePlan() });

    expect(result.current).toMatchObject({ hour: 0, playing: false, variable: "snow" });
    advance(PLAY_STEP_MS * 3);
    expect(result.current.hour).toBe(0);
  });
});
