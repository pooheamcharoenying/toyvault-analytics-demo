# app/utils/digital_ocean_functions.py
from __future__ import annotations
import logging
from typing import Optional, Dict
import boto3
from botocore.client import Config
from io import BytesIO
from pathlib import Path
import pandas as pd
import datetime
import re
import hashlib
import json
import os

logger = logging.getLogger(__name__)

# ---------- Local file cache ----------
CACHE_DIR = Path(os.environ.get("EXCEL_CACHE_DIR", ".excel_cache"))
CACHE_META_FILE = CACHE_DIR / "_meta.json"

def _get_s3_client(region: str, access_key: str, secret_key: str):
    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://{region}.digitaloceanspaces.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )

def upload_fileobj_to_digitalocean(
    fileobj,
    filename: str,
    space_name: str,
    region: str,
    access_key: str,
    secret_key: str,
    content_type: str = "application/octet-stream",
) -> str:
    client = _get_s3_client(region, access_key, secret_key)
    client.upload_fileobj(
        Fileobj=fileobj,
        Bucket=space_name,
        Key=filename,
        ExtraArgs={"ACL": "public-read", "ContentType": content_type},
    )
    return f"https://{space_name}.{region}.digitaloceanspaces.com/{filename}"


def find_latest_excel_key(
    space_name: str,
    region: str,
    access_key: str,
    secret_key: str,
    prefix: str = "",
) -> Optional[str]:
    """
    Return the .xlsx key under `prefix` whose basename contains 'Sale Nichi Data'
    and ends with '(YYYYMMDD).xlsx', choosing the largest YYYYMMDD. If multiple
    share the same YYYYMMDD, prefer the one with newer LastModified. Returns None
    if no matching objects are found.
    """
    client = _get_s3_client(region, access_key, secret_key)

    paginator = client.get_paginator("list_objects_v2")
    date_tag_re = re.compile(r"\((\d{8})\)\.xlsx$", re.IGNORECASE)

    best_key: Optional[str] = None
    best_date: int = -1           # numeric YYYYMMDD
    best_ts = None                # S3's LastModified

    for page in paginator.paginate(Bucket=space_name, Prefix=prefix or ""):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if not key:
                continue

            # Work on the basename only (ignore any "folders" in the key)
            basename = key.rsplit("/", 1)[-1]
            low = basename.lower()

            # Must contain "toyvault demo data" and end with .xlsx
            if "toyvault demo data" not in low or not low.endswith(".xlsx"):
                continue

            # Must end with a bracket date (YYYYMMDD) just before the extension
            m = date_tag_re.search(basename)
            if not m:
                continue

            try:
                date_val = int(m.group(1))  # e.g., 20250915
            except ValueError:
                continue

            ts = obj.get("LastModified")  # tz-aware datetime or None from S3

            # Primary: larger YYYYMMDD wins
            if date_val > best_date:
                best_key, best_date, best_ts = key, date_val, ts
            # Tiebreaker: if same date, prefer newer LastModified
            elif date_val == best_date:
                if best_ts is None and ts is not None:
                    best_key, best_date, best_ts = key, date_val, ts
                elif ts is not None and best_ts is not None and ts > best_ts:
                    best_key, best_date, best_ts = key, date_val, ts

    # Optional fallback: if nothing matched the strict pattern, you could fall back
    # to your previous LastModified-based logic here.
    return best_key

def _safe_cache_name(key: str) -> str:
    """Convert an S3 key into a safe local filename."""
    basename = key.rsplit("/", 1)[-1]
    safe = re.sub(r'[^\w\-.()\[\] ]', '_', basename)
    return safe


def _read_cache_meta() -> dict:
    """Read the cache metadata file."""
    if CACHE_META_FILE.exists():
        try:
            return json.loads(CACHE_META_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_cache_meta(meta: dict):
    """Write cache metadata."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_META_FILE.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")


def _cache_get(key: str) -> Optional[bytes]:
    """Return cached file bytes if key matches, else None."""
    meta = _read_cache_meta()
    if meta.get("key") != key:
        return None
    cached_path = CACHE_DIR / meta.get("local_file", "")
    if cached_path.exists():
        logger.info("Cache hit — loading from local cache: %s", cached_path)
        return cached_path.read_bytes()
    return None


def _cache_put(key: str, body: bytes):
    """Save file bytes to the local cache directory."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local_file = _safe_cache_name(key)
    cached_path = CACHE_DIR / local_file
    cached_path.write_bytes(body)
    _write_cache_meta({
        "key": key,
        "local_file": local_file,
        "size_bytes": len(body),
        "cached_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    logger.info("Cache write — saved %s bytes to %s", f"{len(body):,}", cached_path)


def _parse_excel_bytes(body: bytes) -> Dict[str, pd.DataFrame]:
    """Parse the standard set of sheets from Excel bytes."""
    buf = BytesIO(body)
    sale = pd.read_excel(buf, sheet_name="Sale")
    buf.seek(0)
    onhand = pd.read_excel(buf, sheet_name="OnHand")
    buf.seek(0)
    master = pd.read_excel(buf, sheet_name="Item Master")
    buf.seek(0)
    grpo_detail = pd.read_excel(buf, sheet_name="GRPO Detail")
    buf.seek(0)
    whs_code = pd.read_excel(buf, sheet_name="Whs Code")
    buf.seek(0)
    tr_in = pd.read_excel(buf, sheet_name="TR IN")
    buf.seek(0)
    tr_out = pd.read_excel(buf, sheet_name="TR Out")
    return {
        "sale": sale, "onhand": onhand, "master": master,
        "grpo_detail": grpo_detail, "whs_code": whs_code,
        "tr_in": tr_in, "tr_out": tr_out,
    }


def fetch_excel_to_dfs(
    space_name: str,
    region: str,
    access_key: str,
    secret_key: str,
    key: str,
) -> Dict[str, pd.DataFrame]:
    """
    Streams an Excel file from Spaces and returns a dict of DataFrames.
    Uses a local file cache: if the same key was fetched before and is
    still cached, loads from disk instead of re-downloading.
    """
    # Try the cache first
    cached_body = _cache_get(key)
    if cached_body is not None:
        return _parse_excel_bytes(cached_body)

    # Cache miss — download from Spaces
    logger.info("Cache miss — downloading from Spaces: %s", key)
    client = _get_s3_client(region, access_key, secret_key)
    obj = client.get_object(Bucket=space_name, Key=key)
    body = obj["Body"].read()  # bytes

    # Save to cache for next restart
    _cache_put(key, body)

    return _parse_excel_bytes(body)
