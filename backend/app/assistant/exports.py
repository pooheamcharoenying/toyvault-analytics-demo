"""One-off file exports (Excel / CSV) with short-lived download links.

The AI assistant can't attach a file to a LINE chat — LINE's Messaging API has no
file/document message type. So instead it generates the table the user just saw
as an ``.xlsx`` / ``.csv``, stores the bytes in Mongo under an unguessable token
with a 1-hour TTL, and hands the user a tap-to-download link served by the PUBLIC
``/api/export/{token}`` route. Security is the unguessable token + short expiry.
"""
from __future__ import annotations

import csv
import io
import logging
import secrets
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLLECTION = "exports"
TTL_SECONDS = 3600  # download links expire after 1 hour

CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
}

_index_ready = False


def _coll():
    from app.utils import mongo_store as ms
    db = ms.get_db()
    if db is None:
        return None
    global _index_ready
    c = db[COLLECTION]
    if not _index_ready:
        try:
            c.create_index("created_at", expireAfterSeconds=TTL_SECONDS)
            _index_ready = True
        except Exception:
            logger.exception("exports TTL index create failed (non-fatal)")
    return c


def _norm_fmt(fmt) -> str:
    return "csv" if str(fmt or "").lower() == "csv" else "xlsx"


def _safe_filename(title, fmt) -> str:
    base = "".join(ch if (ch.isalnum() or ch in " -_") else "_" for ch in (title or "table"))
    base = (base.strip() or "table")[:60].replace(" ", "_")
    return f"{base}.{fmt}"


def _build_xlsx(title, columns, rows) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = (str(title or "Data")[:31] or "Data")   # Excel sheet-name cap = 31
    ws.append([str(c) for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(c) for c in columns])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_csv(title, columns, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([str(c) for c in columns])
    for r in rows:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in columns])
    # utf-8-sig (BOM) so Excel opens Thai text correctly
    return buf.getvalue().encode("utf-8-sig")


def build_bytes(title, columns, rows, fmt="xlsx") -> bytes:
    fmt = _norm_fmt(fmt)
    return _build_csv(title, columns, rows) if fmt == "csv" else _build_xlsx(title, columns, rows)


def create_export(title, columns, rows, fmt="xlsx"):
    """Build the file, store it under a token, and return
    ``{token, filename, url, format}`` — or ``None`` if there's nothing to export
    or Mongo is unavailable."""
    if not columns or not rows:
        return None
    fmt = _norm_fmt(fmt)
    c = _coll()
    if c is None:
        return None
    try:
        data = build_bytes(title, columns, rows, fmt)
    except Exception:
        logger.exception("export build failed")
        return None
    from bson import Binary
    from app.core.config import get_settings
    token = secrets.token_urlsafe(16)
    filename = _safe_filename(title, fmt)
    try:
        c.insert_one({
            "_id": token, "filename": filename, "content_type": CONTENT_TYPES[fmt],
            "data": Binary(data), "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        logger.exception("export store failed")
        return None
    base = (get_settings().PUBLIC_BASE_URL or "").rstrip("/")
    return {"token": token, "filename": filename, "format": fmt,
            "url": f"{base}/api/export/{token}"}


def get_export(token):
    """Retrieve a stored export by token, or ``None`` if missing/expired."""
    c = _coll()
    if c is None:
        return None
    doc = c.find_one({"_id": token})
    if not doc:
        return None
    return {"filename": doc.get("filename", "table.xlsx"),
            "content_type": doc.get("content_type", "application/octet-stream"),
            "data": bytes(doc.get("data") or b"")}
