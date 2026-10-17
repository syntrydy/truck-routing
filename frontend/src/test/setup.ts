import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Testing Library only moves a fake clock forward while waiting if it finds Jest's API; give it
// the Vitest equivalent, or any wait under fake timers hangs.
vi.stubGlobal("jest", {
  advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms),
});

afterEach(() => {
  cleanup();
});
