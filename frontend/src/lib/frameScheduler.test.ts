import { describe, expect, it, vi } from "vitest";

import { createFrameScheduler } from "./frameScheduler.ts";

/** A stand-in for the browser's animation frames that runs only when told to. */
function fakeFrames() {
  const callbacks = new Map<number, () => void>();
  let next = 1;
  return {
    request: (callback: () => void) => {
      callbacks.set(next, callback);
      return next++;
    },
    cancel: vi.fn((handle: number) => {
      callbacks.delete(handle);
    }),
    /** The browser draws a frame. */
    tick() {
      const waiting = [...callbacks.values()];
      callbacks.clear();
      waiting.forEach((callback) => {
        callback();
      });
    },
    get waiting() {
      return callbacks.size;
    },
  };
}

describe("createFrameScheduler", () => {
  it("applies the frame number on the next animation frame, not before", () => {
    const frames = fakeFrames();
    const apply = vi.fn();

    createFrameScheduler(apply, frames.request, frames.cancel).schedule(7);
    expect(apply).not.toHaveBeenCalled();
    frames.tick();

    expect(apply).toHaveBeenCalledExactlyOnceWith(7);
  });

  it("applies only the last number asked for within one frame", () => {
    const frames = fakeFrames();
    const apply = vi.fn();
    const scheduler = createFrameScheduler(apply, frames.request, frames.cancel);

    [1, 2, 3, 4, 5].forEach((index) => {
      scheduler.schedule(index);
    });

    expect(frames.waiting).toBe(1); // one request, however many numbers
    frames.tick();
    expect(apply).toHaveBeenCalledExactlyOnceWith(5);
  });

  it("works again for the frame after", () => {
    const frames = fakeFrames();
    const apply = vi.fn();
    const scheduler = createFrameScheduler(apply, frames.request, frames.cancel);

    scheduler.schedule(1);
    frames.tick();
    scheduler.schedule(2);
    frames.tick();

    expect(apply.mock.calls).toEqual([[1], [2]]);
  });

  it("applies nothing that was cancelled", () => {
    const frames = fakeFrames();
    const apply = vi.fn();
    const scheduler = createFrameScheduler(apply, frames.request, frames.cancel);

    scheduler.schedule(3);
    scheduler.cancel();
    frames.tick();

    expect(apply).not.toHaveBeenCalled();
    expect(frames.cancel).toHaveBeenCalledTimes(1);
  });

  it("can be cancelled when nothing waits, and used afterwards", () => {
    const frames = fakeFrames();
    const apply = vi.fn();
    const scheduler = createFrameScheduler(apply, frames.request, frames.cancel);

    scheduler.cancel();
    scheduler.schedule(9);
    frames.tick();

    expect(frames.cancel).not.toHaveBeenCalled();
    expect(apply).toHaveBeenCalledExactlyOnceWith(9);
  });

  it("uses the browser's animation frames by default", () => {
    const request = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 1;
    });
    const apply = vi.fn();

    createFrameScheduler(apply).schedule(4);

    expect(apply).toHaveBeenCalledWith(4);
    request.mockRestore();
  });
});
