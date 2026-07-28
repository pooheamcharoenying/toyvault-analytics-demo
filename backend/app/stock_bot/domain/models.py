"""Domain dataclasses for the stock allocation bot.

Pure Python. No pandas, no I/O. These are the "nouns" the engine layer
operates on. Adapters produce them from pandas frames; the planner consumes
them and produces TransferProposals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class ItemLocationState:
    """Everything the bot needs to know about one (item × location) pair.

    Built by ``engine.targets.compute_item_location_states()`` by joining
    velocity, on-hand, margin, item-size class, location class, and
    shelf-capacity model outputs.
    """
    item_code: str
    item_name: str
    brand: str

    whs_code: str
    whs_name: str

    # Stock state
    on_hand: float                          # current units at this location
    master_price_thb: float                 # list price
    on_hand_thb_master: float               # on_hand × master_price

    # Demand
    velocity_per_day: float                 # observed last 90 days
    velocity_potential_per_day: float       # what the location would absorb if well-stocked
    velocity_basis: str                     # "observed" | "peer" | "policy_override"

    # Lifetime (all-time) sales of this item at this location — the long-run
    # product-market-fit signal.
    sold_qty_lifetime: float
    sold_thb_lifetime: float

    # Margin (per unit, in THB)
    fob_thb_unit: float
    gp_commission_pct: float
    margin_per_unit_thb: float

    # Classifications
    item_size_class: str
    item_size_basis: str
    item_size_evidence: str

    location_class: str
    location_basis: str
    location_evidence: str

    # Shelf capacity (the key new constraint)
    shelf_capacity: int
    shelf_capacity_basis: str
    shelf_capacity_modifiers: tuple[str, ...] = field(default_factory=tuple)

    # Targets
    target_stock: int = 0
    surplus: int = 0
    deficit: int = 0


@dataclass(frozen=True)
class Allocation:
    """Internal solver output: send ``qty`` units of ``item_code`` from source to dest.

    Solvers produce these per-item. Planner converts them to TransferProposals
    by attaching rationale + audit fields from the matching ItemLocationStates.
    """
    item_code: str
    source: str          # WhsCode
    dest: str            # WhsCode
    qty: int


@dataclass(frozen=True)
class TransferProposal:
    """A single recommended transfer, ready for display in Priority Actions.

    All audit fields are populated so a manager can click "Why this?" and see
    the full derivation chain.
    """
    item_code: str
    item_name: str
    brand: str

    qty: int
    from_whs_code: str
    from_whs_name: str
    to_whs_code: str
    to_whs_name: str

    # Source state at the time the plan was generated
    current_qty_at_source: float
    source_days_cover: float
    source_sold_qty_lifetime: float

    # Destination state
    current_qty_at_destination: float
    destination_days_cover: float
    destination_velocity_per_day: float
    destination_velocity_basis: str
    destination_sold_qty_lifetime: float

    # Shelf cap audit
    shelf_capacity_estimate: int
    shelf_capacity_basis: str
    shelf_capacity_modifiers: tuple[str, ...]

    # Money
    master_price_thb: float
    margin_per_unit_thb: float
    transfer_value_thb_master: float
    expected_profit_uplift_thb: float
    score: float

    # Priority ranking — used for the final sort + per-destination cap so
    # proven-seller stockouts at top stores can't lose their slot to a
    # niche high-margin item. Equals expected_profit_uplift × stockout
    # urgency multiplier. NOT a money value — purely a ranking number.
    priority_score: float = 0.0
    stockout_urgency: float = 1.0

    rationale: str = ""
    severity: str = ""   # "high" | "medium" | "low"


@dataclass(frozen=True)
class Divergence:
    """Records a case where the primary and secondary solvers disagreed on
    objective value for one item's allocation. Empty list of divergences =
    the math holds.
    """
    item_code: str
    primary_value: float
    secondary_value: float
    gap_thb: float
    gap_pct: float


@dataclass(frozen=True)
class ComparisonReport:
    """Attached to plan metadata. Verdict is the single number that matters."""
    solver_primary: str
    solver_secondary: str
    items_compared: int
    items_with_transfers: int
    divergence_count: int
    divergence_total_thb: float
    max_divergence_thb_per_item: float
    primary_runtime_ms: float
    secondary_runtime_ms: float
    tolerance_thb: float
    separability_assertion_violations: int
    verdict: str                  # "MATCH" | "MISMATCH"
    divergences: tuple[Divergence, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AllocationPlan:
    """The final plan returned by the planner. The output layer reformats this
    into the JSON shape documented in blueprint §6."""
    generated_at: datetime
    as_of_data_date: Optional[date]
    proposals: tuple[TransferProposal, ...]
    comparison_report: Optional[ComparisonReport] = None
    filters: dict = field(default_factory=dict)   # {year, brand}
