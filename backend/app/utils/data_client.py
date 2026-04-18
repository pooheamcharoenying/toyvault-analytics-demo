"""
Data client — fetches DataFrames from the Data Server (dev) or Spaces (prod).

If DATA_SERVER_URL is set (e.g. http://localhost:8001), fetches pre-parsed
Parquet frames from the Data Server. Otherwise, falls back to the existing
Spaces download + Excel parse path.

This module is the ONLY place the Compute Server decides where data comes from.
"""
from __future__ import annotations

import io
import logging
import os
import time
from typing import Any, Dict, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

from app.utils import helper_functions as hf

DATA_SERVER_URL = os.environ.get("DATA_SERVER_URL", "").rstrip("/")

SHEETS = ["sale", "onhand", "master", "grpo_detail", "whs_code", "tr_in", "tr_out"]

# Timeout: how long to wait for Data Server to be ready (seconds)
_READY_TIMEOUT = 120
_POLL_INTERVAL = 2


def _wait_for_data_server() -> bool:
    """Poll Data Server /data/status until state=ready or timeout."""
    deadline = time.time() + _READY_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(f"{DATA_SERVER_URL}/data/status", timeout=5)
            if r.ok:
                status = r.json()
                state = status.get("state", "")
                if state == "ready":
                    return True
                if state == "error":
                    logger.error("Data Server reported error: %s", status.get('error'))
                    return False
                # Still loading — wait
                logger.info("Data Server state: %s, waiting...", state)
        except requests.ConnectionError:
            logger.info("Data Server not reachable yet, retrying...")
        except Exception as e:
            logger.warning("Unexpected error polling Data Server: %s", e)
        time.sleep(_POLL_INTERVAL)

    logger.error("Timed out waiting for Data Server after %ds", _READY_TIMEOUT)
    return False


def _fetch_frame(sheet_name: str) -> Optional[pd.DataFrame]:
    """Fetch a single DataFrame from Data Server as Parquet."""
    try:
        r = requests.get(f"{DATA_SERVER_URL}/data/frames/{sheet_name}", timeout=30)
        if r.status_code == 200:
            buf = io.BytesIO(r.content)
            return pd.read_parquet(buf, engine="pyarrow")
        else:
            logger.warning("Failed to fetch %s: HTTP %d", sheet_name, r.status_code)
            return None
    except Exception as e:
        logger.error("Error fetching %s: %s", sheet_name, e)
        return None


def _fetch_metadata() -> Optional[dict]:
    """Fetch filename and filedate from Data Server."""
    try:
        r = requests.get(f"{DATA_SERVER_URL}/data/frames_all", timeout=10)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def load_from_data_server() -> bool:
    """
    Fetch all DataFrames from the Data Server and populate GLOBAL_DF.
    Returns True on success, False on failure (caller should fall back to Spaces).
    """
    if not DATA_SERVER_URL:
        return False

    logger.info("DATA_SERVER_URL is set: %s", DATA_SERVER_URL)
    logger.info("Waiting for Data Server to be ready...")

    if not _wait_for_data_server():
        logger.warning("Data Server not available, will fall back to Spaces")
        return False

    hf._set_status(state="loading", filename="(from data server)", error=None)

    # Fetch metadata
    meta = _fetch_metadata()
    filename = meta.get("filename") if meta else None
    filedate_str = meta.get("filedate") if meta else None

    # Fetch each sheet
    frames: Dict[str, Optional[pd.DataFrame]] = {}
    for sheet in SHEETS:
        logger.info("Fetching %s...", sheet)
        df = _fetch_frame(sheet)
        frames[sheet] = df
        if df is not None:
            logger.info("  %s: %d rows", sheet, len(df))
        else:
            logger.warning("  %s: None (not available)", sheet)

    # Check minimum required sheets
    required = ["sale", "onhand", "master"]
    missing = [s for s in required if frames.get(s) is None]
    if missing:
        hf._set_status(state="error", error=f"Data Server missing required sheets: {missing}")
        return False

    # Parse filedate
    filedate = None
    if filedate_str and filedate_str != "None":
        try:
            filedate = hf.extract_date_from_filename(filename or "")
        except Exception:
            pass

    # Populate GLOBAL_DF
    with hf.GLOBAL_DF_LOCK:
        hf.GLOBAL_DF.clear()
        hf.GLOBAL_DF["filename"] = filename
        hf.GLOBAL_DF["filedate"] = filedate
        for sheet in SHEETS:
            hf.GLOBAL_DF[sheet] = frames.get(sheet)

    hf._set_status(state="ready", filename=filename, error=None)
    logger.info("All frames loaded from Data Server")
    return True
