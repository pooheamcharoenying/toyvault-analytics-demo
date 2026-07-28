"""Convert TransferProposals to the Priority Actions schema."""
from __future__ import annotations

from app.stock_bot.domain.models import TransferProposal


def to_priority_action(p: TransferProposal) -> dict:
    """Single TransferProposal → flat Priority Action dict.

    Schema matches ``actions_engine.compute_priority_actions`` output so the
    bot's transfers can be merged into the existing Actions surface.
    """
    title = (
        f"Transfer {p.qty}× {p.item_code} → {p.to_whs_name}"
    )
    return {
        "type": "transfer",
        "severity": p.severity,
        "title": title,
        "reason": p.rationale,
        "impact_thb": round(p.expected_profit_uplift_thb, 2),
        "item_code": p.item_code,
        "brand": p.brand,
        "link": f"/dashboards/item-detail?itemCode={p.item_code}",
        "source": "stock_bot",
    }
