"""LINE rendering for the assistant's tables — plain-text and Flex Message.

LINE has no HTML tables, but **Flex Messages** let us build a table-like card out
of nested Flexbox boxes. We render a header row + data rows into a ``giga`` bubble
for a much nicer look than the plain-text list. Flex has no horizontal scroll and
a size cap, so:
  - wide tables (> MAX_FLEX_COLS columns) fall back to plain text,
  - only the first MAX_FLEX_ROWS rows are shown (full data lives in the Excel/CSV
    export and the web app),
  - the plain-text render is always attached as the Flex ``altText`` (shown in
    notifications and on any client that can't render the card).
"""
from __future__ import annotations

MAX_FLEX_COLS = 6      # more columns than this is unreadable on a phone -> plain text
MAX_FLEX_ROWS = 12     # keep the bubble within LINE's size limits
CELL_BUDGET = 36       # cols × rows shown — above this LINE rejects the bubble (400);
                       # 6×12 fails, 6×6 and 3×12 pass, so cap total cells here

_COL_LABELS = {
    "item_name": "Item", "item_code": "Code", "name": "Name", "brand": "Brand",
    "location": "Location", "channel": "Channel", "period": "Period", "month": "Month",
    "onhand_qty": "On-hand Qty", "onhand_thb": "On-hand ฿",
    "sold_qty": "Sold Qty", "sold_thb": "Revenue ฿", "sold_master_thb": "Revenue (Master) ฿",
    "revenue_thb": "Revenue ฿", "revenue_master_thb": "Revenue (Master) ฿",
    "revenue_actual_thb": "Revenue ฿", "qty": "Qty",
    "days_cover": "Days Cover", "days_of_cover": "Days Cover",
    "margin_pct": "Margin %", "margin_thb": "Margin ฿", "gross_margin_thb": "Margin ฿",
    "cogs_thb": "COGS ฿", "gp_commission_thb": "GP Comm. ฿",
    "sell_through_rate": "Sell-Through %", "dead_stock_pct": "Dead Stock %",
}


def _humanize_col(c: str) -> str:
    if c in _COL_LABELS:
        return _COL_LABELS[c]
    s = c.replace("_thb", " ฿").replace("_pct", " %").replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else c


def _abbrev_money(v: float) -> str:
    a = abs(float(v))
    if a >= 1_000_000:
        return f"฿{v / 1_000_000:,.1f}M"
    if a >= 1_000:
        return f"฿{v / 1_000:,.0f}K"
    return f"฿{v:,.0f}"


def _fmt_val(col: str, v) -> str:
    if v is None or v == "":
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        lc = col.lower()
        if lc.endswith("_thb") or "revenue" in lc or lc in ("onhand_thb", "capital_at_risk"):
            return _abbrev_money(v)
        if lc.endswith("_pct") or lc.endswith("_rate") or "pct" in lc:
            return f"{v:,.1f}%"
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
    return str(v)


def _presentation_to_text(pres: dict, max_rows: int = 15) -> str:
    """Render the chosen table as a readable plain-text numbered list: a name
    column leads each row, a legend line explains the values, money abbreviated
    (฿10.6M). Long lists are capped with a pointer to the web app / export. Also
    used as the Flex ``altText``."""
    cols = list((pres or {}).get("columns") or [])
    rows = (pres or {}).get("rows") or []
    title = (pres or {}).get("title") or "Data"
    total = (pres or {}).get("total_available") or len(rows)
    if not cols or not rows:
        return ""

    label_col = cols[0]              # _apply_presentation guarantees a label first
    value_cols = cols[1:]
    out = [f"📊 {title}"]
    if value_cols:
        out.append("(" + " · ".join(_humanize_col(c) for c in value_cols) + ")")

    shown = rows[:max_rows]
    for i, r in enumerate(shown, 1):
        lbl = r.get(label_col)
        lbl = str(lbl).strip() if lbl not in (None, "") else "(unnamed)"
        if value_cols:
            vals = " · ".join(_fmt_val(c, r.get(c)) for c in value_cols)
            out.append(f"{i}. {lbl} — {vals}")
        else:
            out.append(f"{i}. {lbl}")

    if total > len(shown):
        out.append(f"… {total} rows total. Full sortable table + CSV in the web app.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Flex Message table card
# ---------------------------------------------------------------------------
def _cell(text, *, flex: int, header: bool = False, align: str = "start", wrap: bool = False) -> dict:
    c = {"type": "text", "text": (str(text) if text not in (None, "") else "-"),
         "size": "xs", "flex": flex, "align": align, "wrap": wrap}
    if header:
        c["weight"] = "bold"
        c["color"] = "#555555"
    return c


def build_table_flex(pres: dict, version: str | None = None,
                     max_rows: int = MAX_FLEX_ROWS) -> dict | None:
    """Build a LINE Flex Message rendering `pres` as a table card, or None if the
    table is unsuitable for a phone card (no columns/rows, or too many columns —
    the caller then falls back to plain text)."""
    cols = list((pres or {}).get("columns") or [])
    rows = (pres or {}).get("rows") or []
    if not cols or not rows or len(cols) > MAX_FLEX_COLS:
        return None

    title = (pres or {}).get("title") or "Data"
    total = (pres or {}).get("total_available") or len(rows)
    # Cap shown rows by a cell budget (cols × rows) so LINE accepts the bubble.
    row_cap = min(max_rows, max(2, CELL_BUDGET // len(cols)))
    shown = rows[:row_cap]

    label_col, value_cols = cols[0], cols[1:]
    label_flex, val_flex = 5, 3

    def row_box(r, header=False):
        cells = [_cell(_humanize_col(label_col) if header else r.get(label_col),
                       flex=label_flex, header=header, wrap=not header)]
        for c in value_cols:
            cells.append(_cell(_humanize_col(c) if header else _fmt_val(c, r.get(c)),
                               flex=val_flex, header=header, align="end"))
        return {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": cells}

    contents = [
        {"type": "text", "text": str(title), "weight": "bold", "size": "sm",
         "wrap": True, "color": "#1a3a8f"},
        {"type": "separator", "margin": "sm"},
        row_box({}, header=True),
        {"type": "separator", "margin": "xs"},
    ]
    for i, r in enumerate(shown):
        contents.append(row_box(r))
        if i < len(shown) - 1:
            contents.append({"type": "separator", "margin": "xs", "color": "#EEEEEE"})
    if total > len(shown):
        contents.append({"type": "text", "margin": "sm", "size": "xxs", "wrap": True,
                         "color": "#999999",
                         "text": f"… {total} rows total — full table & CSV in the web app / export"})

    bubble = {
        "type": "bubble", "size": "giga",
        "body": {"type": "box", "layout": "vertical", "spacing": "xs",
                 "paddingAll": "12px", "contents": contents},
    }
    if version:
        bubble["footer"] = {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": f"ToyVault AI v{version}", "size": "xxs",
             "color": "#AAAAAA", "align": "end"}]}

    alt = _presentation_to_text(pres) or str(title)
    if len(alt) > 1490:                # LINE hard limit: altText 0–1500 chars
        alt = alt[:1489] + "…"
    return {"type": "flex", "altText": alt, "contents": bubble}


def _external_browser_url(url: str) -> str:
    """LINE's in-app browser can't download files. Appending ``openExternalBrowser=1``
    makes LINE open the link in the phone's real browser (Chrome/Safari), where the
    download works."""
    if not url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}openExternalBrowser=1"


def build_download_flex(download: dict) -> dict | None:
    """A small Flex bubble with a tap-to-download button for a file export, or
    None if there's no download. Nicer than a raw URL in the text."""
    url = (download or {}).get("url")
    if not url:
        return None
    tap_url = _external_browser_url(url)          # force external browser to allow download
    fn = download.get("filename", "file")
    fmt = str(download.get("format") or "").upper()
    label = (f"⬇ Download {fmt}" if fmt else "⬇ Download")[:20]   # LINE label cap = 20
    bubble = {
        "type": "bubble", "size": "kilo",
        "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
            {"type": "text", "text": f"📎 {fn}", "size": "sm", "wrap": True,
             "weight": "bold", "color": "#1a3a8f"},
            {"type": "text", "text": "Opens in your browser to download · link valid ~1 hour",
             "size": "xxs", "color": "#999999", "wrap": True},
            {"type": "button", "style": "primary", "color": "#1a3a8f", "height": "sm",
             "action": {"type": "uri", "label": label, "uri": tap_url}},
        ]},
    }
    return {"type": "flex", "altText": f"Download {fn}: {tap_url}", "contents": bubble}
