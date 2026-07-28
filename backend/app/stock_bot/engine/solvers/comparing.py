"""Comparing solver — runs primary + secondary, records divergences.

Returns the primary's allocation (deterministic + explainable for users).
Tracks any cases where the secondary finds a higher objective value than
the primary, which would indicate the math has silently broken.

Builds a ComparisonReport after the run that the planner attaches to plan
metadata. ``verdict == "MATCH"`` is the runtime invariant the bot guarantees
under separable-cost assumptions.
"""
from __future__ import annotations

import time
from typing import Any

from app.stock_bot import config
from app.stock_bot.domain.models import Allocation, ComparisonReport, Divergence


class ComparingSolver:
    """Wraps two solvers. Always returns primary; reports divergences."""

    def __init__(
        self,
        primary: Any,
        secondary: Any,
        tolerance_thb: float = config.COMPARISON_TOLERANCE_THB,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.tolerance = tolerance_thb
        self._divergences: list[Divergence] = []
        self._items_compared = 0
        self._items_with_transfers = 0
        self._primary_runtime = 0.0
        self._secondary_runtime = 0.0

    @property
    def name(self) -> str:
        return f"Comparing({self.primary.name}, {self.secondary.name})"

    def solve_single_item(
        self,
        item_code: str,
        supplies: dict[str, int],
        demands: dict[str, int],
        unit_scores: dict[tuple[str, str], float],
        **kwargs,
    ) -> list[Allocation]:
        # Primary first.
        t0 = time.perf_counter()
        primary_alloc = self.primary.solve_single_item(
            item_code, supplies, demands, unit_scores, **kwargs
        )
        self._primary_runtime += time.perf_counter() - t0

        # Secondary for verification.
        t0 = time.perf_counter()
        secondary_alloc = self.secondary.solve_single_item(
            item_code, supplies, demands, unit_scores, **kwargs
        )
        self._secondary_runtime += time.perf_counter() - t0

        self._items_compared += 1
        if primary_alloc or secondary_alloc:
            self._items_with_transfers += 1

        # Compare on objective VALUE, not allocation tuples. Ties / equivalent
        # routings with identical total profit are not divergences.
        primary_value = _objective_value(primary_alloc, unit_scores)
        secondary_value = _objective_value(secondary_alloc, unit_scores)
        gap = secondary_value - primary_value

        if abs(gap) > self.tolerance:
            denom = max(abs(secondary_value), 1.0)
            self._divergences.append(Divergence(
                item_code=item_code,
                primary_value=primary_value,
                secondary_value=secondary_value,
                gap_thb=gap,
                gap_pct=gap / denom,
            ))

        return primary_alloc

    def build_report(self) -> ComparisonReport:
        divergence_thbs = [abs(d.gap_thb) for d in self._divergences]
        return ComparisonReport(
            solver_primary=self.primary.name,
            solver_secondary=self.secondary.name,
            items_compared=self._items_compared,
            items_with_transfers=self._items_with_transfers,
            divergence_count=len(self._divergences),
            divergence_total_thb=sum(divergence_thbs),
            max_divergence_thb_per_item=max(divergence_thbs) if divergence_thbs else 0.0,
            primary_runtime_ms=self._primary_runtime * 1000.0,
            secondary_runtime_ms=self._secondary_runtime * 1000.0,
            tolerance_thb=self.tolerance,
            separability_assertion_violations=getattr(
                self.primary, "separability_violations", 0
            ),
            verdict="MATCH" if not self._divergences else "MISMATCH",
            divergences=tuple(self._divergences),
        )


def _objective_value(
    allocations: list[Allocation],
    unit_scores: dict[tuple[str, str], float],
) -> float:
    return sum(
        a.qty * unit_scores.get((a.source, a.dest), 0.0) for a in allocations
    )
