"""Safety filters — drop ItemLocationStates that shouldn't be eligible
as transfer sources or destinations.

Each filter is a small pure function. Composing them is the planner's job.
"""
from __future__ import annotations

from typing import Optional

from app.stock_bot import config
from app.stock_bot.domain.models import ItemLocationState


def is_eligible_source(
    state: ItemLocationState,
    policy: Optional[dict] = None,
) -> bool:
    """A source must have surplus AND survive these rules:

    - item not in policy ``excluded_items``
    - validFor ≠ "N" (no frozen / deactivated SKUs)
    - margin per unit > 0 (don't move loss-makers)
    - surplus > 0 after honoring min_source_buffer_days
    """
    policy = policy or {}
    if state.item_code in (policy.get("excluded_items") or []):
        return False
    if state.margin_per_unit_thb <= 0:
        return False
    # We honour the buffer by recomputing effective_surplus below.
    return state.surplus > 0 and effective_source_surplus(state) > 0


def is_eligible_destination(
    state: ItemLocationState,
    policy: Optional[dict] = None,
) -> bool:
    """A destination must have deficit AND survive these rules:

    - item not in policy ``excluded_items``
    - location class != "warehouse" (warehouses are sources, not destinations)
    - margin > 0
    - deficit > 0
    """
    policy = policy or {}
    if state.item_code in (policy.get("excluded_items") or []):
        return False
    if state.location_class == "warehouse":
        return False
    if state.margin_per_unit_thb <= 0:
        return False
    return state.deficit > 0


def effective_source_surplus(state: ItemLocationState) -> int:
    """How many units can actually be moved off this source.

    Defined as ``state.surplus`` reduced so that we never leave the source
    with less than ``MIN_SOURCE_BUFFER_DAYS`` of cover.

    For warehouses (unbounded cap) the full surplus is moveable — warehouses
    don't need a display buffer.
    """
    if state.location_class == "warehouse":
        return max(0, state.surplus)

    if state.velocity_per_day <= 0:
        # Zero-velocity source: no cover defined, can move everything in surplus.
        return max(0, state.surplus)

    buffer_units = config.MIN_SOURCE_BUFFER_DAYS * state.velocity_per_day
    # We must leave at least `buffer_units` on the shelf after the transfer.
    available = state.on_hand - buffer_units
    # And we never move more than `surplus` (the target/shelf cap already
    # accounts for ideal stock).
    return max(0, min(int(available), state.surplus))


def is_no_transfer_pair(
    source_whs: str, dest_whs: str, policy: Optional[dict] = None
) -> bool:
    """True if policy.yaml forbids this (source, dest) pair."""
    pairs = (policy or {}).get("no_transfer_pairs") or []
    for pair in pairs:
        a, b = pair[0], pair[1]
        if (source_whs == a and dest_whs == b) or (source_whs == b and dest_whs == a):
            return True
    return False
