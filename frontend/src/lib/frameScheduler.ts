export interface FrameScheduler {
  /** Ask for `index` to be applied on the next animation frame; the latest ask wins. */
  schedule: (index: number) => void;
  /** Drop what is waiting. */
  cancel: () => void;
}

/**
 * Applies a frame number at most once per animation frame. A slider can report many values
 * between two frames; only the last one is worth drawing, and drawing it is the costly part.
 */
export function createFrameScheduler(
  apply: (index: number) => void,
  request: (callback: () => void) => number = (callback) => requestAnimationFrame(callback),
  cancelRequest: (handle: number) => void = (handle) => {
    cancelAnimationFrame(handle);
  },
): FrameScheduler {
  let pending: number | null = null;
  let handle: number | null = null;
  return {
    schedule(index) {
      pending = index;
      handle ??= request(() => {
        handle = null;
        const next = pending;
        pending = null;
        if (next !== null) {
          apply(next);
        }
      });
    },
    cancel() {
      if (handle !== null) {
        cancelRequest(handle);
      }
      handle = null;
      pending = null;
    },
  };
}
