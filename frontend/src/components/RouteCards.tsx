import { memo, useEffect, useRef } from "react";

import type { PlanResponse } from "../api/types.ts";
import { RouteCard } from "./RouteCard.tsx";

interface RouteCardsProps {
  plan: PlanResponse;
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (routeId: string) => void;
  onHover: (routeId: string | null) => void;
}

/** The routes of a plan, best first, to compare and choose from. */
export const RouteCards = memo(function RouteCards({
  plan,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
}: RouteCardsProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  // A new plan has arrived: move focus to its results, so a keyboard or screen reader user
  // starts reading them rather than the form they have just left.
  useEffect(() => {
    heading.current?.focus();
  }, [plan]);

  if (plan.routes.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby="route-cards-heading" className="route-cards">
      <h2 id="route-cards-heading" ref={heading} tabIndex={-1}>
        Routes
      </h2>
      <ol className="route-cards__list">
        {plan.routes.map((route) => (
          <RouteCard
            key={route.id}
            route={route}
            recommended={route.id === plan.recommended_route_id}
            reason={route.id === plan.recommended_route_id ? plan.recommendation_reason : null}
            selected={route.id === selectedId}
            hovered={route.id === hoveredId}
            onSelect={() => {
              onSelect(route.id);
            }}
            onHover={(hovering) => {
              onHover(hovering ? route.id : null);
            }}
          />
        ))}
      </ol>
    </section>
  );
});
