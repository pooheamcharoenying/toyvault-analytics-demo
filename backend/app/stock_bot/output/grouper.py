"""Group TransferProposals by **physical location** for the UI.

One physical store like Siam Paragon is split across many SAP WhsCodes
(GP25, GP33, Art Toy department, etc.). The bot's destination cards group
by the physical location so a manager can review the whole plan for that
store at once. Each transfer row still shows its exact SAP-code destination
for audit, but the grouping key is the physical place.

See ``physical_location.derive_physical_location`` for the normalisation
rules and the policy.yaml override channel.
"""
from __future__ import annotations

from typing import Optional

from app.stock_bot.domain.models import TransferProposal
from app.stock_bot.output.physical_location import derive_physical_location


def group_by_destination(
    proposals: list[TransferProposal],
    policy: Optional[dict] = None,
) -> list[dict]:
    """Group proposals by destination *physical* location.

    Two SAP WhsCodes that normalise to the same physical_location key
    (e.g. ``CTMSYN30`` and ``CTMSYN33`` → ``"M-สยาพารากอน"``) are merged
    into one group. The per-transfer SAP detail is preserved on each row.

    Groups are sorted by total expected profit uplift descending.
    """
    policy = policy or {}
    overrides = policy.get("physical_location_overrides") or {}

    by_key: dict[str, dict] = {}
    for p in proposals:
        key = derive_physical_location(p.to_whs_name, p.to_whs_code, overrides)
        g = by_key.setdefault(key, {
            "physical_location": key,
            "destination_whs_name": key,    # what the UI shows as the group title
            "destination_whs_code": key,    # legacy field, kept for back-compat
            "sap_codes": set(),
            "sap_code_names": {},           # whs_code → whs_name for the detail table
            "transfers": [],
            "_uplift": 0.0,
            "_value": 0.0,
            "_qty": 0,
        })
        g["transfers"].append(_proposal_to_dict(p))
        g["sap_codes"].add(p.to_whs_code)
        g["sap_code_names"][p.to_whs_code] = p.to_whs_name
        g["_uplift"] += p.expected_profit_uplift_thb
        g["_value"] += p.transfer_value_thb_master
        g["_qty"] += p.qty

    groups: list[dict] = []
    for g in by_key.values():
        sap_codes_sorted = sorted(g["sap_codes"])
        groups.append({
            "physical_location": g["physical_location"],
            "destination_whs_name": g["destination_whs_name"],
            "destination_whs_code": g["destination_whs_code"],
            "sap_code_count": len(sap_codes_sorted),
            "sap_codes": sap_codes_sorted,
            "sap_code_names": [
                {"whs_code": c, "whs_name": g["sap_code_names"][c]}
                for c in sap_codes_sorted
            ],
            "summary": {
                "transfer_count": len(g["transfers"]),
                "total_qty": g["_qty"],
                "total_transfer_value_thb_master": round(g["_value"], 2),
                "expected_profit_uplift_thb": round(g["_uplift"], 2),
            },
            # Transfers are sorted within the group by profit uplift descending
            # so the most impactful row shows first under each physical location.
            "transfers": sorted(
                g["transfers"],
                key=lambda t: t["expected_profit_uplift_thb"],
                reverse=True,
            ),
        })

    groups.sort(
        key=lambda g: g["summary"]["expected_profit_uplift_thb"], reverse=True
    )
    return groups


def _proposal_to_dict(p: TransferProposal) -> dict:
    """Serialise a single proposal for the UI / API response.

    NOTE: ``to_whs_code`` and ``to_whs_name`` ARE included now (previously
    omitted because the group held them). They're needed at the row level
    so the UI can show the exact SAP destination under the physical-location
    group header.
    """
    return {
        "item_code": p.item_code,
        "item_name": p.item_name,
        "brand": p.brand,
        "qty": p.qty,
        "from_whs_code": p.from_whs_code,
        "from_whs_name": p.from_whs_name,
        "to_whs_code": p.to_whs_code,
        "to_whs_name": p.to_whs_name,
        "current_qty_at_source": round(p.current_qty_at_source, 2),
        "source_days_cover": _serialise_float(p.source_days_cover),
        "source_sold_qty_lifetime": round(p.source_sold_qty_lifetime, 2),
        "current_qty_at_destination": round(p.current_qty_at_destination, 2),
        "destination_days_cover": _serialise_float(p.destination_days_cover),
        "destination_velocity_per_day": round(p.destination_velocity_per_day, 4),
        "destination_velocity_basis": p.destination_velocity_basis,
        "destination_sold_qty_lifetime": round(p.destination_sold_qty_lifetime, 2),
        "shelf_capacity_estimate": p.shelf_capacity_estimate,
        "shelf_capacity_basis": p.shelf_capacity_basis,
        "shelf_capacity_modifiers": list(p.shelf_capacity_modifiers),
        "master_price_thb": round(p.master_price_thb, 2),
        "margin_per_unit_thb": round(p.margin_per_unit_thb, 2),
        "transfer_value_thb_master": round(p.transfer_value_thb_master, 2),
        "expected_profit_uplift_thb": round(p.expected_profit_uplift_thb, 2),
        "score": round(p.score, 2),
        "priority_score": round(p.priority_score, 2),
        "stockout_urgency": round(p.stockout_urgency, 2),
        "rationale": p.rationale,
        "severity": p.severity,
    }


def _serialise_float(x: float) -> float | None:
    """Replace ±inf with None so JSON serialisation doesn't blow up."""
    if x == float("inf") or x == float("-inf") or x != x:  # NaN check
        return None
    return round(x, 2)
