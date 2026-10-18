import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDelayedFlag } from "./useDelayedFlag.ts";
import { useElapsedSeconds } from "./useElapsedSeconds.ts";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

const advance = (ms: number) => {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
};

describe("useDelayedFlag", () => {
  it("is false until the delay has passed", () => {
    const { result } = renderHook(() => useDelayedFlag(true, 3000));

    expect(result.current).toBe(false);
    advance(2999);
    expect(result.current).toBe(false);
    advance(1);
    expect(result.current).toBe(true);
  });

  it("is false while inactive, and starts counting again when it becomes active", () => {
    const { result, rerender } = renderHook(({ active }) => useDelayedFlag(active, 3000), {
      initialProps: { active: false },
    });
    advance(10_000);
    expect(result.current).toBe(false);

    rerender({ active: true });
    advance(2000);
    expect(result.current).toBe(false);
    advance(1000);
    expect(result.current).toBe(true);
  });

  it("goes false as soon as it stops being active, and needs the whole delay again", () => {
    const { result, rerender } = renderHook(({ active }) => useDelayedFlag(active, 3000), {
      initialProps: { active: true },
    });
    advance(3000);
    expect(result.current).toBe(true);

    rerender({ active: false });
    expect(result.current).toBe(false);
    rerender({ active: true });
    expect(result.current).toBe(false);
    advance(3000);
    expect(result.current).toBe(true);
  });

  it("leaves no timer behind", () => {
    const { unmount } = renderHook(() => useDelayedFlag(true, 3000));

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("useElapsedSeconds", () => {
  it("counts whole seconds while active", () => {
    const { result } = renderHook(() => useElapsedSeconds(true));

    expect(result.current).toBe(0);
    advance(999);
    expect(result.current).toBe(0);
    advance(1);
    expect(result.current).toBe(1);
    advance(4000);
    expect(result.current).toBe(5);
  });

  it("is 0 while inactive, and starts from 0 again", () => {
    const { result, rerender } = renderHook(({ active }) => useElapsedSeconds(active), {
      initialProps: { active: true },
    });
    advance(5000);
    expect(result.current).toBe(5);

    rerender({ active: false });
    expect(result.current).toBe(0);
    advance(5000);
    expect(result.current).toBe(0);
    rerender({ active: true });
    advance(2000);
    expect(result.current).toBe(2);
  });

  it("leaves no timer behind", () => {
    const { unmount } = renderHook(() => useElapsedSeconds(true));

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
