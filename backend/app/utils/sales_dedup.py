"""Legacy line-level sales dedup — gated behind a flag, OFF by default.

WHY THIS MODULE EXISTS
----------------------
Every analytics helper used to collapse "duplicate" Sale rows on a key like
``(DocEntry, ItemCode, Period, GroupName, WhsCode)`` before aggregating,
"to avoid over-counting". That assumption is wrong for this data.

The SAP Sale export has **no LineNum**. On consignment settlement documents
it emits **one byte-identical row per unit sold** — three units of the same
item, same document, same store, same day appear as three identical rows.
There is no field that distinguishes them because there is nothing to
distinguish: they are three real sales. Collapsing them deletes real revenue.

VERIFIED (July 2026), against the V.1.4 (20260717) workbook:
  * MN18031 @ Grandway Riverside: 87 units transferred in, 87 sold, 0 on-hand.
    Reconciles to exactly 0 ONLY on raw lines. The dedup reported 60 sold
    and implied 27 phantom units still on the shelf.
  * Falsification test across 88,732 item-location pairs: raw sales produce
    essentially the same "impossible oversell" count as deduped (34,953 vs
    34,668) — i.e. the removed rows are NOT duplicates, they are real sales.
  * On the 6,214 pairs the dedup altered, RAW reconciles exactly to SAP
    on-hand 26.0% of the time vs 1.2% for deduped.
  * Company-wide the dedup was hiding ~48,900 sale lines / ~102,800 units /
    ~THB 28.7M (4.72% of revenue).

DocEntry is NOT a stable document id (22% span multiple dates/DocNums) and
DocTotal does not equal sum(LineTotal) even 40% of the time, so neither can
be used to reconcile "true" duplicates out. There are none to remove.

HISTORY
-------
  * Oct 2025 (75e85e0): dedup introduced with no documented case, just the
    comment "avoid over-counting".
  * May 2026 (5522bdc): WhsCode added to the key after it was found to drop
    ~89k rows across multi-store chains (AeroBot @ Grandway World read 52
    units vs Grandway's own 57). Correct as far as it went, but did not
    question the underlying line-collapse — which still drops repeated
    unit-sales within a single (DocEntry, ItemCode, Period, WhsCode) group.

THE FLAG
--------
Default (unset or ``off``): NO line-level dedup — every real unit-sale row is
kept. This is the correct behaviour.

``SALES_LINE_DEDUP=on``: restores the old line-collapse, for rollback and
for before/after dashboard comparison only.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence

import pandas as pd

# Standard candidate key, preserved from the pre-fix call sites so that
# flag-ON behaviour is byte-identical to the old code.
DEFAULT_KEY = ["DocEntry", "ItemCode", "Period", "GroupName", "WhsCode"]


def line_dedup_enabled() -> bool:
    """True only when SALES_LINE_DEDUP is explicitly turned on.

    Accepts on/1/true/yes (case-insensitive). Anything else — including the
    variable being unset — means the correct (no-dedup) behaviour.
    """
    return os.environ.get("SALES_LINE_DEDUP", "off").strip().lower() in (
        "on", "1", "true", "yes",
    )


def dedup_sale_lines(
    df: pd.DataFrame,
    subset: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Apply the legacy line-level dedup ONLY when the flag is on.

    Default returns ``df`` unchanged — keeping every real unit-sale row.
    When ``SALES_LINE_DEDUP=on``, drops duplicates on ``subset`` (or
    :data:`DEFAULT_KEY`), filtered to the columns actually present, exactly
    as the old code did.

    Safe on ``None``/empty inputs.
    """
    if df is None or getattr(df, "empty", True):
        return df
    if not line_dedup_enabled():
        return df
    candidates = list(subset) if subset is not None else DEFAULT_KEY
    cols = [c for c in candidates if c in df.columns]
    if not cols:
        return df
    return df.drop_duplicates(subset=cols)
