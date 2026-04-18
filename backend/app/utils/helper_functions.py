# app/utils/helper_functions.py
from __future__ import annotations
import logging
from typing import Any, Optional
from fastapi import BackgroundTasks
import threading
import pandas as pd
import os
from datetime import datetime, timezone
import re
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

# Import the DO fetcher (no circular imports)
from app.utils.digital_ocean_functions import fetch_excel_to_dfs

# ------------- Shared in-memory state -------------
GLOBAL_DF: dict[str, Any] = {
    "filename": None,
    "filedate": None,
    "sale": None,
    "onhand": None,
    "master": None,
    "grpo_detail": None,
    "whs_code": None,
    "tr_in": None,
    "tr_out": None,
}
GLOBAL_DF_LOCK = threading.Lock()

# If you want to keep a local upload folder for the /upload route:
UPLOAD_DIR = "uploads"

LOAD_STATUS = {
    "state": "idle",       # 'idle' | 'loading' | 'ready' | 'error'
    "filename": None,
    "error": None,
    "updated_at": None,
}

def _ext_from_filename(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _set_status(**kwargs):
    LOAD_STATUS.update(kwargs)
    LOAD_STATUS["updated_at"] = _utc_now_iso()

# ------------- Local-file loader (kept for /upload) -------------
def _extract_file_to_global_df(saved_path: str, ext: str):
    global GLOBAL_DF
    _set_status(state="loading", filename=os.path.basename(saved_path), error=None, rows=None, cols=None)
    engine = "xlrd" if ext == ".xls" else "openpyxl"
    try:
        sale   = pd.read_excel(saved_path, sheet_name="Sale", engine=engine)
        onhand = pd.read_excel(saved_path, sheet_name="OnHand", engine=engine)
        master = pd.read_excel(saved_path, sheet_name="Item Master", engine=engine)
        grpo_detail = pd.read_excel(saved_path, sheet_name="GRPO Detail", engine=engine)
        whs_code = pd.read_excel(saved_path, sheet_name="Whs Code", engine=engine)
        tr_in = pd.read_excel(saved_path, sheet_name="TR IN", engine=engine)
        tr_out = pd.read_excel(saved_path, sheet_name="TR Out", engine=engine)        

        logger.info("Excel data loaded and ready")
        with GLOBAL_DF_LOCK:
            GLOBAL_DF = {"filename": os.path.basename(saved_path), "filedate": extract_date_from_filename(os.path.basename(saved_path)), "sale": sale, "onhand": onhand, "master": master, "grpo_detail": grpo_detail, "whs_code": whs_code, "tr_in": tr_in, "tr_out": tr_out}
        _set_status(state="ready", rows=None, cols=None, error=None)
    except Exception as e:
        _set_status(state="error", error=str(e), rows=None, cols=None)

def schedule_load_from_path(saved_path: str, ext: Optional[str] = None, background_tasks: Optional[BackgroundTasks] = None) -> None:
    ext = (ext or _ext_from_filename(saved_path)).lower()
    if background_tasks is not None:
        background_tasks.add_task(_extract_file_to_global_df, saved_path, ext)
    else:
        threading.Thread(target=_extract_file_to_global_df, args=(saved_path, ext), daemon=True).start()

def extract_date_from_filename(filename: str):
    """
    Extracts a YYYYMMDD date inside parentheses from the filename.
    Returns a datetime.date object, or None if no date found.
    """
    match = re.search(r"\((\d{8})\)", filename)
    if match:
        date_str = match.group(1)
        # Convert to datetime.date
        return datetime.strptime(date_str, "%Y%m%d").date()
    return None

# ------------- Spaces loader (new) -------------
def _extract_spaces_key_to_global_df(
    space_name: str,
    region: str,
    access_key: str,
    secret_key: str,
    key: str,
):
    """
    Background worker: fetch Excel from Spaces (key) and populate GLOBAL_DF.
    """
    global GLOBAL_DF
    _set_status(state="loading", filename=key, error=None, rows=None, cols=None)
    try:
        dfs = fetch_excel_to_dfs(space_name=space_name, region=region, access_key=access_key, secret_key=secret_key, key=key)
        with GLOBAL_DF_LOCK:
            GLOBAL_DF = {"filename": key, "filedate": extract_date_from_filename(key), "sale": dfs["sale"], "onhand": dfs["onhand"], "master": dfs["master"], "grpo_detail": dfs["grpo_detail"], "whs_code": dfs["whs_code"], "tr_in": dfs["tr_in"], "tr_out": dfs["tr_out"]}
        _set_status(state="ready", rows=None, cols=None, error=None)
    except Exception as e:
        _set_status(state="error", error=str(e), rows=None, cols=None)

def schedule_load_from_spaces_key(
    *,
    space_name: str,
    region: str,
    access_key: str,
    secret_key: str,
    key: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> None:
    """
    Schedule a background job to load from Spaces object `key` into GLOBAL_DF.
    """
    if background_tasks is not None:
        background_tasks.add_task(_extract_spaces_key_to_global_df, space_name, region, access_key, secret_key, key)
    else:
        threading.Thread(
            target=_extract_spaces_key_to_global_df,
            args=(space_name, region, access_key, secret_key, key),
            daemon=True,
        ).start()

# ------------- (Optional) keep your local folder scanner -------------
_DATE_TAG = re.compile(r"\((\d{8})\)(?=\.(?:xlsx|xls)$)", re.IGNORECASE)

def find_latest_excel(upload_dir: str = UPLOAD_DIR) -> Optional[Path]:
    p = Path(upload_dir)
    if not p.exists():
        return None
    files = list(p.glob("*.xlsx")) + list(p.glob("*.xls"))
    if not files:
        return None
    tagged: list[tuple[datetime, Path]] = []
    untagged: list[Path] = []
    for f in files:
        m = _DATE_TAG.search(f.name)
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%Y%m%d")
                tagged.append((dt, f))
            except ValueError:
                untagged.append(f)
        else:
            untagged.append(f)
    if tagged:
        max_date = max(t[0] for t in tagged)
        same_day = [f for d, f in tagged if d == max_date]
        return max(same_day, key=lambda f: f.stat().st_mtime)
    return max(files, key=lambda f: f.stat().st_mtime)



def df_to_jsonable_head(df: pd.DataFrame, n: int = 5):
    if not isinstance(df, pd.DataFrame):
        return None
    out = df.head(n)
    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.astype(object).where(out.notna(), None)
    return out.to_dict(orient="records")