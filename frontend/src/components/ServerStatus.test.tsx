import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoA11yViolations } from "../test/axe.ts";
import { COLD_START_AFTER_MS, ServerStatus } from "./ServerStatus.tsx";

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

describe("ServerStatus", () => {
  it("waits three seconds, as the SPEC says", () => {
    expect(COLD_START_AFTER_MS).toBe(3000);
  });

  it("says nothing while the server answers quickly", () => {
    const { container, rerender } = render(<ServerStatus waking failed={false} />);
    advance(2999);
    expect(container).toBeEmptyDOMElement();

    rerender(<ServerStatus waking={false} failed={false} />);
    advance(10_000);
    expect(container).toBeEmptyDOMElement();
  });

  it("says the server is waking up once it is slow", () => {
    render(<ServerStatus waking failed={false} />);

    advance(3000);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Waking up the server…");
    expect(status).toHaveTextContent("up to a minute");
  });

  it("takes the message away when the server answers", () => {
    const { rerender } = render(<ServerStatus waking failed={false} />);
    advance(5000);
    expect(screen.getByRole("status")).toBeInTheDocument();

    rerender(<ServerStatus waking={false} failed={false} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says when the server is not answering at all, urgently", () => {
    render(<ServerStatus waking={false} failed />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The server is not answering.");
    expect(alert).toHaveTextContent("reload the page");
  });

  it("has no accessibility violations in either state", async () => {
    vi.useRealTimers();
    const { container, rerender } = render(<ServerStatus waking={false} failed />);
    await expectNoA11yViolations(container);

    rerender(<ServerStatus waking={false} failed={false} />);
    await expectNoA11yViolations(container);
  });
});
