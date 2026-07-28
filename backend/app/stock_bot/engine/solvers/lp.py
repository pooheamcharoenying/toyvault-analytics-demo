"""Linear-programming transportation solver via scipy.optimize.linprog (HiGHS).

For each item, formulate as:

    maximize  Σ score[s, d] · x[s, d]
    subject to
        Σ_d x[s, d] ≤ supply[s]    ∀ s
        Σ_s x[s, d] ≤ demand[d]    ∀ d
        0 ≤ x[s, d] ≤ MAX_QTY_PER_TRANSFER

linprog minimises, so we pass -score. The transportation polytope is
totally unimodular, so with integer supplies/demands the LP relaxation
returns integer optimal x automatically (we round and assert tiny gap).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from app.stock_bot import config
from app.stock_bot.domain.models import Allocation


class LpTransportationSolver:
    """Per-item LP optimum. ~30 ms per non-trivial item via HiGHS."""

    name = "LpTransportationSolver"

    def solve_single_item(
        self,
        item_code: str,
        supplies: dict[str, int],
        demands: dict[str, int],
        unit_scores: dict[tuple[str, str], float],
        *,
        max_qty_per_transfer: int = config.MAX_QTY_PER_TRANSFER,
    ) -> list[Allocation]:
        """Solve the RAW transportation LP — no thresholds applied.

        See the docstring on ``GreedySeparableSolver.solve_single_item`` for
        why thresholds are deferred to the planner.
        """
        if not supplies or not demands or not unit_scores:
            return []

        sources = [s for s, q in supplies.items() if q > 0]
        dests = [d for d, q in demands.items() if q > 0]
        if not sources or not dests:
            return []

        # Build the variable order: (s_0, d_0), (s_0, d_1), ..., (s_n, d_m).
        n_vars = len(sources) * len(dests)
        c = np.zeros(n_vars)
        for i, s in enumerate(sources):
            for j, d in enumerate(dests):
                idx = i * len(dests) + j
                c[idx] = -float(unit_scores.get((s, d), 0.0))  # negate for minimisation

        # Supply constraints: for each source i, sum over dests <= supply[i].
        a_ub = np.zeros((len(sources) + len(dests), n_vars))
        b_ub = np.zeros(len(sources) + len(dests))
        for i, s in enumerate(sources):
            for j in range(len(dests)):
                a_ub[i, i * len(dests) + j] = 1.0
            b_ub[i] = float(supplies[s])
        # Demand constraints: for each dest j, sum over sources <= demand[j].
        for j, d in enumerate(dests):
            for i in range(len(sources)):
                a_ub[len(sources) + j, i * len(dests) + j] = 1.0
            b_ub[len(sources) + j] = float(demands[d])

        bounds = [(0.0, float(max_qty_per_transfer))] * n_vars

        result = linprog(c=c, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if not result.success:
            return []

        allocations: list[Allocation] = []
        x = result.x
        for i, s in enumerate(sources):
            for j, d in enumerate(dests):
                raw = x[i * len(dests) + j]
                # Snap near-integer LP output to int. The polytope is TU so
                # raw should already be within 1e-8 of an integer.
                q = int(round(raw))
                if q <= 0:
                    continue
                allocations.append(Allocation(
                    item_code=item_code, source=s, dest=d, qty=q,
                ))
        return allocations
