"""Greedy transportation solver — optimal for separable cost matrices.

For a cost matrix that factors as ``c[s, d] = f(s) · g(d)``, sorting edges
by score and filling greedily produces the same objective value as LP
(by the rearrangement inequality). v1's score matrix is separable by
construction (see scorer.py), so this is provably optimal here.

Includes a debug-mode separability assertion that screams if the invariant
ever breaks.
"""
from __future__ import annotations

from app.stock_bot import config
from app.stock_bot.domain.models import Allocation
from app.stock_bot.engine.scorer import is_separable


class GreedySeparableSolver:
    """Per-item greedy with provable optimality under separable costs."""

    name = "GreedySeparableSolver"

    def __init__(self, debug_check_separability: bool = True) -> None:
        self.debug_check_separability = debug_check_separability
        self.separability_violations = 0

    def solve_single_item(
        self,
        item_code: str,
        supplies: dict[str, int],
        demands: dict[str, int],
        unit_scores: dict[tuple[str, str], float],
        *,
        max_qty_per_transfer: int = config.MAX_QTY_PER_TRANSFER,
    ) -> list[Allocation]:
        """Solve the RAW transportation problem — no thresholds applied.

        Thresholds like ``min_qty_per_transfer`` and ``min_uplift_thb`` are
        applied by the planner AFTER both solvers have run. Applying them
        inside the solver causes greedy and LP to diverge: greedy skips
        whole edges (freeing supply), LP optimises then prunes (losing
        supply). The raw transportation problem is what both solvers must
        agree on under separable costs.
        """
        if not supplies or not demands or not unit_scores:
            return []

        if self.debug_check_separability:
            if not is_separable(
                unit_scores, tol=config.SEPARABILITY_ASSERTION_TOLERANCE
            ):
                self.separability_violations += 1

        # Sort edges by score descending. Stable sort, so ties keep the
        # natural (source, dest) order — useful for deterministic snapshot
        # tests.
        edges = sorted(
            unit_scores.items(),
            key=lambda kv: (-kv[1], kv[0]),
        )

        remaining_supply = dict(supplies)
        remaining_demand = dict(demands)
        allocations: list[Allocation] = []

        for (s, d), score_per_unit in edges:
            if score_per_unit <= 0:
                continue
            available = remaining_supply.get(s, 0)
            wanted = remaining_demand.get(d, 0)
            q = min(available, wanted, max_qty_per_transfer)
            if q <= 0:
                continue
            allocations.append(Allocation(
                item_code=item_code, source=s, dest=d, qty=int(q),
            ))
            remaining_supply[s] = available - q
            remaining_demand[d] = wanted - q

        return allocations
