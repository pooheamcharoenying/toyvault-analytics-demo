"""Orchestrate the per-item solver loop and produce TransferProposals.

For each item with at least one eligible source and destination, build the
transportation subproblem and hand it to the configured solver. Then
post-process: apply min-impact filter, per-destination cap, sort.
"""
from __future__ import annotations

from typing import Any, Optional

from app.stock_bot import config
from app.stock_bot.domain.models import (
    Allocation,
    ItemLocationState,
    TransferProposal,
)
from app.stock_bot.engine import filters, scorer


def plan_transfers(
    states: list[ItemLocationState],
    solver: Any,
    policy: Optional[dict] = None,
) -> tuple[list[TransferProposal], Any]:
    """Run the per-item solver across all items, collect proposals.

    Returns:
        (proposals, solver) — the solver is returned so the caller can pull
        its comparison report or other side-effect state.
    """
    policy = policy or {}

    # Group states by item.
    by_item: dict[str, list[ItemLocationState]] = {}
    for s in states:
        by_item.setdefault(s.item_code, []).append(s)

    all_allocations: list[tuple[Allocation, ItemLocationState, ItemLocationState]] = []

    for item_code, item_states in by_item.items():
        # Eligible sources and destinations for this item.
        sources = [s for s in item_states if filters.is_eligible_source(s, policy)]
        dests = [s for s in item_states if filters.is_eligible_destination(s, policy)]
        if not sources or not dests:
            continue

        # Supplies, demands, and the SEPARABLE score matrix.
        supplies = {s.whs_code: filters.effective_source_surplus(s) for s in sources}
        # Re-drop zero entries (might have been clamped by the buffer).
        supplies = {k: v for k, v in supplies.items() if v > 0}
        if not supplies:
            continue
        demands = {d.whs_code: d.deficit for d in dests}

        unit_scores: dict[tuple[str, str], float] = {}
        src_by_code = {s.whs_code: s for s in sources}
        dst_by_code = {d.whs_code: d for d in dests}
        margin = sources[0].margin_per_unit_thb  # margin is per-item constant
        for sc in supplies:
            for dc in demands:
                if filters.is_no_transfer_pair(sc, dc, policy):
                    continue
                unit_scores[(sc, dc)] = scorer.unit_score(
                    margin, src_by_code[sc], dst_by_code[dc]
                )

        if not unit_scores:
            continue

        raw_allocations = solver.solve_single_item(
            item_code=item_code,
            supplies=supplies,
            demands=demands,
            unit_scores=unit_scores,
        )
        # Apply per-edge thresholds AFTER the solver. Solvers return the raw
        # optimal transportation answer; planner is responsible for "is this
        # transfer worth the operational cost?" filtering. This guarantees
        # greedy and LP solve the same problem and therefore must agree
        # under separable costs (the ComparingSolver invariant).
        for a in raw_allocations:
            if a.qty < config.MIN_QTY_PER_TRANSFER:
                continue
            score_per_unit = unit_scores.get((a.source, a.dest), 0.0)
            if a.qty * score_per_unit < config.MIN_UPLIFT_THB:
                continue
            src_state = src_by_code.get(a.source)
            dst_state = dst_by_code.get(a.dest)
            if src_state is None or dst_state is None:
                continue
            all_allocations.append((a, src_state, dst_state))

    # Build TransferProposal objects.
    proposals: list[TransferProposal] = []
    for a, src, dst in all_allocations:
        prop = _build_proposal(a, src, dst)
        if prop.expected_profit_uplift_thb < config.MIN_IMPACT_THB:
            continue
        proposals.append(prop)

    # ---- Final ranking & truncation (Task #33 / "Level 2") -----------
    #
    # Previously: sort everything by expected_profit_uplift_thb desc,
    # apply per-destination cap, apply global cap. Failure mode: a
    # niche high-margin item could push a proven-seller stockout out
    # of the top-N for a flagship.
    #
    # Now: walk destinations in priority order (sum of priority_score
    # across their candidate proposals = where the biggest stock-fill
    # opportunity sits). Within each destination, sort by priority_score
    # desc (urgency-boosted). Take top-N per destination. Stop when
    # global cap is hit.
    #
    # This guarantees top stores' proven-seller stockouts make it into
    # the output, and the per-destination cap can't silently drop them
    # in favour of niche high-margin recs at other locations.

    by_dest: dict[str, list[TransferProposal]] = {}
    for p in proposals:
        by_dest.setdefault(p.to_whs_code, []).append(p)

    # Rank destinations by total candidate priority — proxy for "biggest
    # opportunity sits here." Correlated with store revenue + stockout
    # severity. Ties broken alphabetically for deterministic output.
    dest_rank = sorted(
        by_dest.keys(),
        key=lambda d: (
            -sum(p.priority_score for p in by_dest[d]),
            d,
        ),
    )

    final: list[TransferProposal] = []
    max_per_dest = config.MAX_TRANSFERS_PER_DESTINATION
    max_total = config.MAX_TRANSFERS_TOTAL
    for dest in dest_rank:
        dest_proposals = sorted(
            by_dest[dest],
            key=lambda p: p.priority_score,
            reverse=True,
        )
        if max_per_dest:
            dest_proposals = dest_proposals[:max_per_dest]
        for p in dest_proposals:
            final.append(p)
            if max_total and len(final) >= max_total:
                break
        if max_total and len(final) >= max_total:
            break

    # The downstream API consumer (output/grouper.py) still wants a
    # globally-sorted list for the priority-actions feed and for the
    # destination-group sort key inside group_by_destination. Sort the
    # surviving proposals by priority_score desc — within a destination
    # this is the same order we chose above, and across destinations it
    # gives a clean global ranking.
    final.sort(key=lambda p: p.priority_score, reverse=True)

    return final, solver


def _build_proposal(
    a: Allocation,
    src: ItemLocationState,
    dst: ItemLocationState,
) -> TransferProposal:
    score_per_unit = scorer.unit_score(src.margin_per_unit_thb, src, dst)
    score = a.qty * score_per_unit
    uplift = a.qty * src.margin_per_unit_thb     # raw expected profit
    transfer_value = a.qty * src.master_price_thb

    # Stockout-urgency boost (Task #33 / "Fix A"). For destinations that
    # have proven sales for this SKU but are currently sitting on little
    # or no stock, multiply the priority by a factor proportional to
    # (lifetime units sold here) / (units currently on the shelf).
    #
    # Why: the previous sort key (expected_profit_uplift_thb only) ranked
    # a niche high-margin product above a proven volume seller. When the
    # per-destination cap then bites at top-N, the proven seller could
    # lose its slot — even though it's the recommendation a planner most
    # wants. Boosting urgency makes "0 on-hand at a 30-sold-here SKU"
    # outrank "5 on-hand at a 6-sold-here SKU" regardless of margin.
    stockout_urgency = _stockout_urgency(dst)
    priority = uplift * stockout_urgency

    src_days_cover = (
        src.on_hand / src.velocity_per_day
        if src.velocity_per_day > 0
        else float("inf")
    )
    dst_days_cover = (
        dst.on_hand / dst.velocity_per_day
        if dst.velocity_per_day > 0
        else float("inf")
    )

    rationale = _build_rationale(a, src, dst, uplift, src_days_cover, dst_days_cover)
    severity = _severity(uplift, src_days_cover)

    return TransferProposal(
        item_code=a.item_code,
        item_name=src.item_name,
        brand=src.brand,
        qty=a.qty,
        from_whs_code=src.whs_code,
        from_whs_name=src.whs_name,
        to_whs_code=dst.whs_code,
        to_whs_name=dst.whs_name,
        current_qty_at_source=src.on_hand,
        source_days_cover=src_days_cover,
        source_sold_qty_lifetime=src.sold_qty_lifetime,
        current_qty_at_destination=dst.on_hand,
        destination_days_cover=dst_days_cover,
        destination_velocity_per_day=dst.velocity_per_day,
        destination_velocity_basis=dst.velocity_basis,
        destination_sold_qty_lifetime=dst.sold_qty_lifetime,
        shelf_capacity_estimate=dst.shelf_capacity,
        shelf_capacity_basis=dst.shelf_capacity_basis,
        shelf_capacity_modifiers=dst.shelf_capacity_modifiers,
        master_price_thb=src.master_price_thb,
        margin_per_unit_thb=src.margin_per_unit_thb,
        transfer_value_thb_master=transfer_value,
        expected_profit_uplift_thb=uplift,
        score=score,
        priority_score=priority,
        stockout_urgency=stockout_urgency,
        rationale=rationale,
        severity=severity,
    )


def _stockout_urgency(dst: ItemLocationState) -> float:
    """Urgency multiplier in [1.0, MAX_STOCKOUT_URGENCY].

    Computed as ``sold_qty_lifetime / max(1, on_hand + 1)``, clamped so:
      - destinations that have NEVER sold this SKU get 1.0 (no boost,
        no penalty — we don't know whether this SKU fits)
      - destinations with healthy on-hand and modest sales hover near 1
      - destinations with proven sales but 0 on-hand can climb to MAX

    A cap protects against runaway multipliers when an item has sold
    hundreds of units but currently shows 0 on-hand. We don't want one
    super-stockout to crowd out every other recommendation.
    """
    lifetime = max(0.0, float(dst.sold_qty_lifetime))
    on_hand = max(0.0, float(dst.on_hand))
    if lifetime <= 0.0:
        return 1.0
    raw = lifetime / max(1.0, on_hand + 1.0)
    if raw < 1.0:
        return 1.0
    return min(raw, MAX_STOCKOUT_URGENCY)


# Cap on the stockout urgency multiplier — protects against a single
# proven-seller-with-zero-stock from monopolising the top of the list.
# Value of 10 means "the most extreme stockout we'll prioritise is 10× a
# nominal sale."
MAX_STOCKOUT_URGENCY = 10.0


def _build_rationale(
    a: Allocation,
    src: ItemLocationState,
    dst: ItemLocationState,
    uplift: float,
    src_days_cover: float,
    dst_days_cover: float,
) -> str:
    src_cover_str = (
        "∞ days (zero velocity)" if src_days_cover == float("inf")
        else f"{src_days_cover:.0f} days"
    )
    dst_cover_str = (
        "∞ days (zero velocity)" if dst_days_cover == float("inf")
        else f"{dst_days_cover:.0f} days"
    )
    return (
        f"{src.whs_name} holds {src.on_hand:.0f} units ({src_cover_str} of cover) "
        f"while {dst.whs_name} has only {dst.on_hand:.0f} ({dst_cover_str}). "
        f"Shelf cap at {dst.whs_name} is {dst.shelf_capacity} "
        f"(basis: {dst.shelf_capacity_basis}). "
        f"Recommending {a.qty} units → expected profit uplift ≈ "
        f"{uplift:,.0f} THB at {src.margin_per_unit_thb:,.0f} THB margin per unit."
    )


def _severity(uplift_thb: float, source_days_cover: float) -> str:
    if uplift_thb >= 10_000 or source_days_cover >= 365:
        return "high"
    if uplift_thb >= 3_000:
        return "medium"
    return "low"
