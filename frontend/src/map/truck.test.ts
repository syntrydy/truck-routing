import { describe, expect, it } from "vitest";

import { checkpoint } from "../test/plan.ts";
import { buildTruckElement, truckPosition } from "./truck.ts";

const at = (iso: string) => Date.parse(iso);
const points = [
  checkpoint(0, { lat: 40, lon: -90, eta: "2026-10-18T10:00:00Z" }),
  checkpoint(1, { lat: 41, lon: -92, eta: "2026-10-18T12:00:00Z" }),
  checkpoint(2, { lat: 41, lon: -96, eta: "2026-10-18T16:00:00Z" }),
];

describe("truckPosition", () => {
  it("waits at the start until the departure", () => {
    expect(truckPosition(points, at("2026-10-18T08:00:00Z"))).toEqual([-90, 40]);
    expect(truckPosition(points, at("2026-10-18T10:00:00Z"))).toEqual([-90, 40]);
  });

  it("is on a checkpoint when it arrives there", () => {
    expect(truckPosition(points, at("2026-10-18T12:00:00Z"))).toEqual([-92, 41]);
  });

  it("is on the line between the checkpoints either side of the moment", () => {
    expect(truckPosition(points, at("2026-10-18T11:00:00Z"))).toEqual([-91, 40.5]);
    expect(truckPosition(points, at("2026-10-18T14:00:00Z"))).toEqual([-94, 41]);
  });

  it("has arrived after the last checkpoint", () => {
    expect(truckPosition(points, at("2026-10-19T09:00:00Z"))).toEqual([-96, 41]);
  });

  it("is at the checkpoint when there is only one", () => {
    expect(truckPosition(points.slice(0, 1), at("2030-01-01T00:00:00Z"))).toEqual([-90, 40]);
  });

  it("is nowhere for a route without checkpoints", () => {
    expect(truckPosition([], at("2026-10-18T10:00:00Z"))).toBeNull();
  });

  it("does not divide by zero when two checkpoints share a time", () => {
    const same = [
      checkpoint(0, { lat: 40, lon: -90, eta: "2026-10-18T10:00:00Z" }),
      checkpoint(1, { lat: 41, lon: -91, eta: "2026-10-18T10:00:00Z" }),
      checkpoint(2, { lat: 42, lon: -92, eta: "2026-10-18T12:00:00Z" }),
    ];

    expect(truckPosition(same, at("2026-10-18T10:30:00Z"))).toEqual([-91.25, 41.25]);
  });
});

describe("buildTruckElement", () => {
  it("is a labelled image with a hidden drawing", () => {
    const element = buildTruckElement();

    expect(element).toHaveAttribute("role", "img");
    expect(element.getAttribute("aria-label")).toMatch(/Truck/);
    expect(element.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
