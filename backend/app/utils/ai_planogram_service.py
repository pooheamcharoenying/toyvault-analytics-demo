"""Service layer for the AI Suggested Planogram.

Runs the demand-ceiling engine (app.demand.engine) once over every managed-shelf
planogram location and caches the result (auto-invalidated when the data file
changes). Endpoints look up a single location's items from that cached map, so a
page load never re-runs the ~15s compute.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _compute_all(**_kwargs) -> Dict[str, Dict[str, dict]]:
    """Compute AI planograms for all planogram locations. Returns
    {loc: {item_code: {ai fields}}}. Empty dict if data or scope is unavailable."""
    from app.utils import helper_functions as hf
    from app.utils import planogram_par as pp
    from app.demand.engine import compute_ai_planograms

    dfs = hf.GLOBAL_DF
    needed = ("sale", "master", "onhand", "grpo_detail", "tr_in", "tr_out", "whs_code")
    if any(dfs.get(k) is None for k in needed):
        return {}
    try:
        scope = pp.all_location_ids()
    except Exception:
        scope = None
    if not scope:
        return {}

    res = compute_ai_planograms(
        dfs.get("sale"), dfs.get("master"), dfs.get("onhand"),
        dfs.get("grpo_detail"), dfs.get("tr_in"), dfs.get("tr_out"),
        dfs.get("whs_code"), scope_locs=scope,
    )
    out: Dict[str, Dict[str, dict]] = {}
    for r in res.to_dict("records"):
        out.setdefault(r["loc"], {})[str(r["item_code"])] = {
            "ai_suggested_planogram": r["planogram_current"],   # this-month target
            "ai_peak_planogram": r["planogram_peak"],
            "ai_peak_month": r["peak_month"],
            "ai_base_demand": r["base_demand"],
            "ai_profile": r["profile"],
            "ai_status": r["status"],
            "ai_confidence": r["confidence"],
            "ai_months_history": r["months_of_history"],
            "ai_seasonal_source": r["seasonal_source"],
            "current_onhand": r["current_onhand"],
        }
    logger.info("AI planograms computed for %d locations", len(out))
    return out


def ai_for_location(location: str) -> Dict[str, dict]:
    """AI planogram fields for every item at ``location`` (keyed by item_code).
    Cached across all locations; auto-invalidates when the data file changes."""
    from app.utils.cache import cached_call
    from app.utils import planogram_par as pp
    try:
        allai = cached_call("ai_planograms_all", _compute_all)
    except Exception:
        logger.exception("AI planogram compute failed")
        return {}
    if location in allai:
        return allai[location]
    # tolerate whitespace/normalization differences in the location id
    norm = pp._norm_id(location)
    for loc, items in allai.items():
        if pp._norm_id(loc) == norm:
            return items
    return {}
