import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "./AppShell.tsx";

describe("AppShell", () => {
  it("lays out the panel, the map and the slider as labelled regions", () => {
    render(<AppShell panel={<p>form</p>} map={<p>the map</p>} slider={<p>the slider</p>} />);

    expect(screen.getByRole("complementary", { name: "Trip planner" })).toHaveTextContent("form");
    expect(screen.getByRole("main")).toHaveTextContent("the map");
    expect(screen.getByRole("region", { name: "Forecast" })).toHaveTextContent("the slider");
  });
});
