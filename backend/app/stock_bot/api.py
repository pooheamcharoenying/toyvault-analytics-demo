"""Stock Bot — public API.

The single public entry point. Everything outside ``app.stock_bot.*`` should
import only from here.
"""
from __future__ import annotations

import math
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    import yaml as _yaml  # PyYAML — optional. policy.yaml is ignored if missing.
except ImportError:  # pragma: no cover
    _yaml = None

from app.stock_bot import config
from app.stock_bot.adapters import (
    consolidation as consol_mod,
    location_quality as locq_mod,
    margin as margin_mod,
    stock_state as stock_mod,
    velocity as velo_mod,
)
from app.stock_bot.domain.models import AllocationPlan
from app.stock_bot.engine import planner as planner_mod
from app.stock_bot.engine import targets as targets_mod
from app.stock_bot.engine.solvers.comparing import ComparingSolver
from app.stock_bot.engine.solvers.greedy import GreedySeparableSolver
from app.stock_bot.engine.solvers.lp import LpTransportationSolver
from app.stock_bot.output import action_formatter, grouper
from app.utils import nichi_stock as nstk


_POLICY_PATH = Path(__file__).parent / "policy.yaml"


def _load_policy() -> dict:
    """Read policy.yaml. Returns empty-section dict if missing, malformed,
    or if PyYAML is not installed in the deploy environment."""
    if _yaml is None or not _POLICY_PATH.exists():
        return {}
    try:
        with open(_POLICY_PATH, "r", encoding="utf-8") as fh:
            data = _yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:  # pragma: no cover — fall back to no overrides
        return {}


def build_all_item_location_states(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    df_grpo_detail: pd.DataFrame,
    year: Optional[int] = None,
    brand: Optional[str] = None,
) -> dict[str, Any]:
    """Run the bot's prep pipeline up through ItemLocationState construction
    and return the states plus the metadata callers need.

    Extracted from ``generate_transfer_plan`` so the location-summary
    endpoint can look up shelf caps for items that have NO transfer
    proposal (the bot still computes a cap for them; we just don't expose
    it from the proposals list).

    Returns dict with keys:
        - ``states`` — list[ItemLocationState] (one per item × location)
        - ``policy`` — loaded policy.yaml dict (overrides + excludes etc)
        - ``as_of_data_date`` — date | None
        - ``df_sale_prep`` — the prepared/filtered sale frame
    """
    policy = _load_policy()
    physical_overrides = policy.get("physical_location_overrides") or {}

    # ---- Consolidate WhsCodes → physical-location labels ----
    # The whole pipeline now operates at one row per (item, physical
    # store), not per SAP code. Fixes the case where a 4-unit shelf cap
    # got split as 2+2 across two SAP codes and both chunks fell below
    # MIN_QTY_PER_TRANSFER. See app/stock_bot/adapters/consolidation.py.
    whs_to_physical = consol_mod.build_whs_to_physical_lookup(
        df_whs_code, policy_overrides=physical_overrides,
    )
    df_raw_sale = consol_mod.consolidate_whs_codes(
        df_raw_sale, whs_to_physical, keep_original_column=False,
    )
    df_raw_onhand = consol_mod.consolidate_whs_codes(
        df_raw_onhand, whs_to_physical, keep_original_column=False,
    )
    df_grpo_detail = consol_mod.consolidate_whs_codes(
        df_grpo_detail, whs_to_physical, keep_original_column=False,
    )
    df_whs_code = consol_mod.consolidate_whs_code_table(
        df_whs_code, whs_to_physical,
    )

    df_sale_prep, df_onhand_prep, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )

    if brand is not None and "Brand" in df_sale_prep.columns:
        df_sale_prep = df_sale_prep[df_sale_prep["Brand"] == brand]
    if year is not None and "DocDate" in df_sale_prep.columns:
        df_sale_prep = df_sale_prep.copy()
        df_sale_prep["DocDate"] = pd.to_datetime(
            df_sale_prep["DocDate"], errors="coerce"
        )
        df_sale_prep = df_sale_prep[df_sale_prep["DocDate"].dt.year == year]

    as_of_data_date: Optional[date] = None
    if "DocDate" in df_sale_prep.columns and not df_sale_prep.empty:
        ts = pd.to_datetime(df_sale_prep["DocDate"], errors="coerce").max()
        if pd.notna(ts):
            as_of_data_date = ts.date()

    velocity_df = velo_mod.build_item_location_velocity(
        df_sale_prep, window_days=90
    )
    lifetime_df = velo_mod.build_item_location_lifetime_sales(df_sale_prep)
    stock_df = stock_mod.build_item_location_onhand(
        df_raw_onhand, df_item_master, df_whs_code
    )
    margin_df = margin_mod.build_item_margin(
        df_grpo_detail, df_item_master,
        typical_gp_pct=config.TYPICAL_GP_COMMISSION_PCT,
    )
    locq_df = locq_mod.build_location_quality(
        df_sale_prep, stock_df, window_days=365
    )

    states = targets_mod.compute_item_location_states(
        stock_df=stock_df,
        velocity_df=velocity_df,
        margin_df=margin_df,
        location_quality_df=locq_df,
        lifetime_df=lifetime_df,
        policy=policy,
    )

    return {
        "states": states,
        "policy": policy,
        "as_of_data_date": as_of_data_date,
        "df_sale_prep": df_sale_prep,
    }


def generate_transfer_plan(
    df_raw_sale: pd.DataFrame,
    df_raw_onhand: pd.DataFrame,
    df_item_master: pd.DataFrame,
    df_whs_code: pd.DataFrame,
    df_grpo_detail: pd.DataFrame,
    year: Optional[int] = None,
    brand: Optional[str] = None,
) -> dict[str, Any]:
    """End-to-end: ingest raw frames → produce a transfer plan dict.

    Returns the JSON shape documented in STOCK_BOT_BLUEPRINT.md §6.
    """
    bundle = build_all_item_location_states(
        df_raw_sale, df_raw_onhand, df_item_master,
        df_whs_code, df_grpo_detail, year=year, brand=brand,
    )
    states = bundle["states"]
    policy = bundle["policy"]
    as_of_data_date = bundle["as_of_data_date"]

    solver = ComparingSolver(
        primary=GreedySeparableSolver(),
        secondary=LpTransportationSolver(),
    ) if config.USE_COMPARING_SOLVER else GreedySeparableSolver()

    proposals, used_solver = planner_mod.plan_transfers(
        states=states, solver=solver, policy=policy
    )

    # 4. Output.
    priority_actions = [action_formatter.to_priority_action(p) for p in proposals]
    destination_groups = grouper.group_by_destination(proposals, policy=policy)

    summary = _summarise(proposals)
    comparison_report = (
        used_solver.build_report()
        if isinstance(used_solver, ComparingSolver)
        else None
    )

    plan = AllocationPlan(
        generated_at=datetime.utcnow(),
        as_of_data_date=as_of_data_date,
        proposals=tuple(proposals),
        comparison_report=comparison_report,
        filters={"year": year, "brand": brand},
    )

    return _serialise(plan, priority_actions, destination_groups, summary)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _summarise(proposals) -> dict:
    return {
        "total_proposals": len(proposals),
        "total_qty": sum(p.qty for p in proposals),
        "total_transfer_value_thb_master": round(
            sum(p.transfer_value_thb_master for p in proposals), 2
        ),
        "total_expected_profit_uplift_thb": round(
            sum(p.expected_profit_uplift_thb for p in proposals), 2
        ),
        "horizon_days": config.HORIZON_DAYS,
        "destinations_covered": len({p.to_whs_code for p in proposals}),
    }


def _serialise(
    plan: AllocationPlan,
    priority_actions: list,
    destination_groups: list,
    summary: dict,
) -> dict:
    report_dict = None
    if plan.comparison_report is not None:
        r = plan.comparison_report
        report_dict = {
            "solver_primary": r.solver_primary,
            "solver_secondary": r.solver_secondary,
            "items_compared": r.items_compared,
            "items_with_transfers": r.items_with_transfers,
            "divergence_count": r.divergence_count,
            "divergence_total_thb": round(r.divergence_total_thb, 2),
            "max_divergence_thb_per_item": round(r.max_divergence_thb_per_item, 2),
            "primary_runtime_ms": round(r.primary_runtime_ms, 2),
            "secondary_runtime_ms": round(r.secondary_runtime_ms, 2),
            "tolerance_thb": r.tolerance_thb,
            "separability_assertion_violations": r.separability_assertion_violations,
            "verdict": r.verdict,
            # Cap divergences in the JSON to avoid huge responses
            "divergences": [
                {
                    "item_code": d.item_code,
                    "primary_value": round(d.primary_value, 2),
                    "secondary_value": round(d.secondary_value, 2),
                    "gap_thb": round(d.gap_thb, 2),
                    "gap_pct": round(d.gap_pct, 4),
                }
                for d in r.divergences[:20]
            ],
        }

    return {
        "status": "ok",
        "generated_at": plan.generated_at.isoformat() + "Z",
        "as_of_data_date": (
            plan.as_of_data_date.isoformat()
            if plan.as_of_data_date else None
        ),
        "filters": plan.filters,
        "summary": summary,
        "priority_actions": priority_actions,
        "destination_groups": destination_groups,
        "comparison_report": report_dict,
    }
