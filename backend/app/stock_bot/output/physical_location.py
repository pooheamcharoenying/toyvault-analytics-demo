"""Derive a single physical-location key for a SAP warehouse entry.

Background: one physical store like Grandway Riverside is split across many
SAP WhsCodes in this data — different commission tiers (GP25, GP33),
different consignment vs credit arrangements, different departments
(Art Toy), promotional pop-ups, etc. A manager planning the day's
transfers thinks "what's going to Grandway Riverside today?" — not "what's
going to CTMSYN25, CTMSYN30, CTMSYN33, ...". The bot's destination
grouping must reflect that.

The rule (kept deliberately simple, with policy.yaml override for any
edge case the auto-derivation gets wrong):

  1. If policy.yaml.physical_location_overrides[whs_code] is set, use it.
  2. Otherwise strip from WhsName:
     - GP-percent suffixes (`GP25`, `GP 33%`)
     - Tier markers (`T1`, `T2`)
     - Discount markers (`ส่วนลด 31-50%`)
     - Parenthesised department / promo info (`(Art Toy)`, `(Gourmet Market)`)
     - Date ranges from promo names (`_1 - 12/08/24`, `5-15/10/23`)
     - Trailing punctuation, collapsed whitespace
  3. The result is the physical_location key. Two SAP entries that
     normalise to the same key get grouped together.

Channel prefix (`M-`, `CT-`, `TRU`, `RO-`) is KEPT — it distinguishes
different tenants at the same mall (Plaza Group vs Grandway vs KidZone at
Grandway Riverside are separate tenants in separate retail spaces and should
not be merged).

Pure function. No pandas, no I/O. Trivially unit-testable.
"""
from __future__ import annotations

import re
from typing import Optional


# Order matters: each regex is applied in sequence to a working string.
# Anchored where possible to avoid eating legitimate parts of a name.
_STRIP_PATTERNS = (
    # GP percent: "GP25", "GP 33%", "GP15%" — with or without surrounding spaces
    re.compile(r"\s*GP\s*\d+\s*%?", re.IGNORECASE),
    # Tier markers as whole words: T1, T2
    re.compile(r"\bT[12]\b"),
    # Thai discount info: "ส่วนลด 31-50%"
    re.compile(r"\s*ส่วนลด[\s\d\-%]+"),
    # Parenthesised aside: "(Art Toy)", "(Gourmet Market)", "(สินค้าเปียกน้ำ)"
    re.compile(r"\s*\([^)]*\)"),
)

# Promo dates anywhere in the string, including multi-segment ones like
# "8-12/01/20" or "_1 - 12/08/24". Repeats `[/-]\d{1-4}` so all segments
# (day-day/month/year) are consumed.
_DATE_PATTERN = re.compile(
    r"[_\s]+\d{1,2}(?:\s*[\-/]\s*\d{1,4})+"
)

# Mid-string promo suffix: everything from " Pro_..." to end-of-string is
# promo metadata and should be stripped. We split on the literal " Pro_"
# rather than using a regex with variable-width lookbehind so a Pro_ at the
# very START of a name (a pop-up location identifier) is preserved.
_PROMO_SEP = " Pro_"

_TRAILING_PUNCT = re.compile(r"[_\-\s]+$")
_WHITESPACE = re.compile(r"\s+")


def derive_physical_location(
    whs_name: str,
    whs_code: Optional[str] = None,
    policy_overrides: Optional[dict] = None,
) -> str:
    """Return the physical-location grouping key for a SAP warehouse entry.

    Args:
        whs_name: The SAP WhsName (e.g. ``"M-Grandway Riverside T1 GP30"``).
        whs_code: The WhsCode (used to look up policy overrides).
        policy_overrides: Dict from ``policy.yaml.physical_location_overrides``
            mapping ``whs_code → physical_location_label``.

    Returns:
        A normalised string used as the grouping key. Falls back to
        ``whs_name`` (or ``whs_code``) if the result would be empty.
    """
    # Layer 1: explicit policy override always wins.
    if whs_code and policy_overrides:
        override = policy_overrides.get(whs_code)
        if override:
            return str(override).strip()

    if whs_name is None:
        return whs_code or ""

    name = str(whs_name).strip()
    if not name or name.lower() == "nan":
        return whs_code or ""

    s = name
    for pat in _STRIP_PATTERNS:
        s = pat.sub(" ", s)
    # Cut mid-string promo suffix (" Pro_..."), but keep a leading "Pro_"
    # which functions as the location identifier itself (pop-up location).
    if _PROMO_SEP in s:
        s = s.split(_PROMO_SEP, 1)[0]
    s = _DATE_PATTERN.sub(" ", s)
    s = _TRAILING_PUNCT.sub("", s)
    s = _WHITESPACE.sub(" ", s).strip(" -_,.")

    # Defensive fallback: if stripping ate everything, return the original.
    return s or name
