"""Consolidate SAP WhsCodes into physical-location identifiers.

The Stock Bot's mental model is the planner's mental model: one entry
per *physical store*, not per SAP commission tier. A single mall like
Grandway Riverside can spread across many SAP WhsCodes (GP25 / GP30 / GP33 /
Art Toy department / promo pop-ups), and a planner thinks of them as
ONE store. The bot should too.

Before this consolidation step, the bot computed caps / velocities /
allocations at the SAP-code level — leading to absurd outcomes where a
4-unit shelf cap got split into 2+2 across two SAP codes, each chunk
fell below MIN_QTY_PER_TRANSFER=3, and the whole recommendation
disappeared.

After consolidation, each (item, physical_location) pair is one row
with the aggregated velocity / on-hand / sales. Caps are sized to the
real store's throughput. Transfer recommendations end up at physical-
location grain — what a planner actually executes against.

Pure pandas transforms. No I/O, no state. The output frames have
``WhsCode`` replaced by the physical-location label (e.g.
``"M-Grandway Riverside"`` rather than ``"CTMSYN30"``). The original WhsCode
is preserved in a new ``OriginalWhsCode`` column for audit.

Used by ``app.stock_bot.api.build_all_item_location_states`` as the
first preprocessing step.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.stock_bot.output.physical_location import derive_physical_location


def build_whs_to_physical_lookup(
    df_whs_code: pd.DataFrame,
    policy_overrides: Optional[dict] = None,
) -> dict[str, str]:
    """Build a {WhsCode -> physical_location_label} dict using the same
    ``derive_physical_location`` helper the output grouper uses.

    Parameters
    ----------
    df_whs_code : DataFrame
        Raw "Whs Code" sheet — must have ``WhsCode`` and ``WhsName``.
    policy_overrides : dict | None
        Optional ``physical_location_overrides`` from policy.yaml.

    Returns
    -------
    dict[str, str]
        WhsCode string → physical-location string. Empty dict if
        ``df_whs_code`` is missing or empty.
    """
    if df_whs_code is None or df_whs_code.empty:
        return {}
    overrides = policy_overrides or {}
    lookup: dict[str, str] = {}
    for _, row in df_whs_code.iterrows():
        code = str(row.get("WhsCode", "")).strip()
        name = str(row.get("WhsName", code)).strip()
        if not code:
            continue
        lookup[code] = derive_physical_location(name, code, overrides)
    return lookup


def consolidate_whs_codes(
    df: Optional[pd.DataFrame],
    whs_to_physical: dict[str, str],
    *,
    keep_original_column: bool = True,
) -> pd.DataFrame:
    """Return a copy of ``df`` with WhsCode replaced by its consolidated
    physical-location label.

    Rows whose WhsCode isn't in the lookup are passed through unchanged
    (their original WhsCode survives as their physical location). This is
    defensive — we never want to silently drop sales / on-hand rows just
    because a WhsCode wasn't in the lookup table.

    Parameters
    ----------
    df : DataFrame | None
        Any frame with a ``WhsCode`` column (Sale, OnHand, GRPO Detail).
    whs_to_physical : dict
        From ``build_whs_to_physical_lookup``.
    keep_original_column : bool
        If True, the pre-consolidation code is preserved as
        ``OriginalWhsCode`` (useful for audit / debugging).

    Returns
    -------
    DataFrame — a *copy* with WhsCode replaced. Empty DataFrame if input
    is empty/None.
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    if "WhsCode" not in df.columns:
        return df.copy()

    out = df.copy()
    code_series = out["WhsCode"].astype(str).str.strip()
    if keep_original_column:
        out["OriginalWhsCode"] = code_series
    out["WhsCode"] = code_series.map(whs_to_physical).fillna(code_series)
    return out


def consolidate_whs_code_table(
    df_whs_code: Optional[pd.DataFrame],
    whs_to_physical: dict[str, str],
) -> pd.DataFrame:
    """Collapse the raw Whs Code lookup table itself so each physical
    location appears once.

    Returns a DataFrame with columns ``WhsCode`` (= physical label) and
    ``WhsName`` (= physical label, since it IS the human-readable name
    after consolidation). One row per unique physical location.

    Empty input → empty output.
    """
    if df_whs_code is None or df_whs_code.empty:
        return pd.DataFrame(columns=["WhsCode", "WhsName"])

    # Apply the lookup; deduplicate.
    consolidated = consolidate_whs_codes(
        df_whs_code, whs_to_physical, keep_original_column=False
    )
    if "WhsName" not in consolidated.columns:
        consolidated["WhsName"] = consolidated["WhsCode"]
    # After consolidation, WhsName should equal WhsCode (both are the
    # physical-location label) so the downstream pipeline shows
    # human-readable names everywhere.
    consolidated["WhsName"] = consolidated["WhsCode"]
    return consolidated[["WhsCode", "WhsName"]].drop_duplicates(
        subset=["WhsCode"]
    ).reset_index(drop=True)
