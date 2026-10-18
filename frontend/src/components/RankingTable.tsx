import { memo } from "react";

import type { PlanResponse } from "../api/types.ts";
import { formatDuration, formatMiles } from "../lib/format.ts";

type Criterion = PlanResponse["ranking"]["criteria"][number];

interface RankingTableProps {
  plan: PlanResponse;
}

/** A value of a criterion as a person reads it: miles, the 0 to 4 risk scale, or a drive time. */
export function formatCriterionValue(unit: Criterion["unit"], value: number | null): string {
  if (value === null) {
    return "unknown";
  }
  if (unit === "mi") {
    return formatMiles(value);
  }
  return unit === "s" ? formatDuration(value) : value.toFixed(2);
}

/**
 * How the routes were ranked, criterion by criterion in the order the ranking applies them,
 * with the row that decided between the two best routes marked. A cell that is the best of
 * its row says so in words and with a mark, so that colour is not what carries it; a row where
 * every route is equally good marks none.
 */
export const RankingTable = memo(function RankingTable({ plan }: RankingTableProps) {
  const { criteria } = plan.ranking;
  const columns = criteria[0]?.values ?? [];
  if (columns.length < 2) {
    return null;
  }
  const labels = new Map(plan.routes.map((route) => [route.id, route.label]));
  const title =
    plan.recommended_route_id === null ? "How the routes were ranked" : "Why this route?";
  return (
    <details className="ranking" open>
      <summary className="ranking__title">{title}</summary>
      <table className="ranking__table">
        <caption className="visually-hidden">
          Routes compared on each criterion, in the order they decide the ranking, best route first
        </caption>
        <thead>
          <tr>
            <td />
            {columns.map(({ route_id: id }) => (
              <th key={id} scope="col">
                {labels.get(id) ?? id}
                {id === plan.recommended_route_id && (
                  <span className="ranking__picked"> (recommended)</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {criteria.map((criterion, index) => {
            const discriminates = criterion.values.some((cell) => !cell.best);
            return (
              <tr key={criterion.id} className={criterion.decisive ? "ranking__row--decisive" : ""}>
                <th scope="row">
                  {index + 1}. {criterion.label}
                  {criterion.decisive && <span className="ranking__decided"> decided here</span>}
                </th>
                {criterion.values.map((cell) => (
                  <td
                    key={cell.route_id}
                    className={cell.best && discriminates ? "ranking__best" : ""}
                  >
                    {formatCriterionValue(criterion.unit, cell.value)}
                    {cell.best && discriminates && (
                      <>
                        {" "}
                        <span aria-hidden="true">✓</span>
                        <span className="visually-hidden"> (best)</span>
                      </>
                    )}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </details>
  );
});
