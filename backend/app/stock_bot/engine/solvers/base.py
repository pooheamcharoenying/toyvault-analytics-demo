"""Transportation solver Protocol — the contract all solvers implement."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.stock_bot.domain.models import Allocation


@runtime_checkable
class TransportationSolver(Protocol):
    """Solver interface.

    Implementations: GreedySeparableSolver, LpTransportationSolver,
    ComparingSolver.
    """

    name: str

    def solve_single_item(
        self,
        item_code: str,
        supplies: dict[str, int],         # {whs_code: units available}
        demands: dict[str, int],          # {whs_code: units wanted}
        unit_scores: dict[tuple[str, str], float],   # {(src, dst): score per unit}
        *,
        max_qty_per_transfer: int = 200,
        min_qty_per_transfer: int = 3,
        min_uplift_thb: float = 500.0,
    ) -> list[Allocation]:
        ...
