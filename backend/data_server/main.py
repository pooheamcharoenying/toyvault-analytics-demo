"""
Data Server — Dev-only FastAPI service that loads Excel once and serves DataFrames.

Start once, leave running. The Compute Server fetches frames from here on startup
so it can restart in <2 seconds without re-parsing the 180MB Excel workbook.

Usage:
    cd "Nichiworld Railway App Backend"
    python -m uvicorn data_server.main:app --host 0.0.0.0 --port 8001

Production (Railway): NOT used — the compute server loads from Spaces directly
when DATA_SERVER_URL is not set.
"""
from __future__ import annotations

import io
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse

# Reuse existing loading infrastructure
from app.utils import digital_ocean_functions as dof
from app.utils import helper_functions as hf
from app.core.config import get_settings

app = FastAPI(title="Nichiworld Data Server (dev-only)")

SHEETS = ["sale", "onhand", "master", "grpo_detail", "whs_code", "tr_in", "tr_out"]


@app.get("/")
def health():
    return {"service": "data-server", "state": hf.LOAD_STATUS.get("state", "idle")}


@app.get("/data/status")
def data_status():
    return JSONResponse(hf.LOAD_STATUS, status_code=200)


@app.get("/data/frames/{sheet_name}")
def get_frame(sheet_name: str):
    """Serve a single DataFrame as Parquet bytes."""
    if hf.LOAD_STATUS.get("state") != "ready":
        raise HTTPException(status_code=503, detail="Data not ready yet")
    if sheet_name not in SHEETS:
        raise HTTPException(status_code=404, detail=f"Unknown sheet: {sheet_name}. Valid: {SHEETS}")

    df = hf.GLOBAL_DF.get(sheet_name)
    if df is None:
        raise HTTPException(status_code=404, detail=f"Sheet '{sheet_name}' is None")

    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    return Response(content=buf.getvalue(), media_type="application/octet-stream")


@app.get("/data/frames_all")
def get_all_frames():
    """Serve all DataFrames as a JSON manifest with Parquet bytes base64-encoded.
    For simplicity, returns metadata — the client fetches each sheet individually.
    """
    if hf.LOAD_STATUS.get("state") != "ready":
        raise HTTPException(status_code=503, detail="Data not ready yet")

    available = []
    for name in SHEETS:
        df = hf.GLOBAL_DF.get(name)
        available.append({
            "sheet": name,
            "rows": len(df) if df is not None else 0,
            "available": df is not None,
        })

    return {
        "state": hf.LOAD_STATUS.get("state"),
        "filename": hf.GLOBAL_DF.get("filename"),
        "filedate": str(hf.GLOBAL_DF.get("filedate")) if hf.GLOBAL_DF.get("filedate") else None,
        "sheets": available,
    }


@app.get("/data/reload")
def reload_data():
    """Force re-download from Spaces (useful after uploading a new file)."""
    settings = get_settings()
    latest_key = dof.find_latest_excel_key(
        space_name=settings.DO_SPACE_NAME,
        region=settings.DO_REGION,
        access_key=settings.DO_ACCESS_KEY,
        secret_key=settings.DO_SECRET_KEY,
        prefix=getattr(settings, "DO_PREFIX", ""),
    )
    if latest_key is None:
        return {"message": "No Excel found in Spaces", "state": "idle"}

    hf.schedule_load_from_spaces_key(
        space_name=settings.DO_SPACE_NAME,
        region=settings.DO_REGION,
        access_key=settings.DO_ACCESS_KEY,
        secret_key=settings.DO_SECRET_KEY,
        key=latest_key,
        background_tasks=None,
    )
    return {"message": f"Reload started for {latest_key}", "state": "loading"}


@app.on_event("startup")
def load_on_startup():
    """Load Excel from local cache on startup (demo mode — no cloud lookup)."""
    import json
    from pathlib import Path

    settings = get_settings()

    # Demo mode: read key from local cache metadata instead of hitting Spaces
    cache_meta = Path(dof.CACHE_DIR) / "_meta.json"
    latest_key = None
    if cache_meta.exists():
        try:
            meta = json.loads(cache_meta.read_text(encoding="utf-8"))
            latest_key = meta.get("key")
        except Exception:
            latest_key = None

    # Fallback to Spaces lookup if no cache
    if latest_key is None:
        try:
            latest_key = dof.find_latest_excel_key(
                space_name=settings.DO_SPACE_NAME,
                region=settings.DO_REGION,
                access_key=settings.DO_ACCESS_KEY,
                secret_key=settings.DO_SECRET_KEY,
                prefix=getattr(settings, "DO_PREFIX", ""),
            )
        except Exception as e:
            hf._set_status(state="idle", filename=None, error=f"No cache and Spaces unreachable: {e}")
            return

    if latest_key is None:
        hf._set_status(state="idle", filename=None, error="No Excel found in cache or Spaces")
        return

    hf.schedule_load_from_spaces_key(
        space_name=settings.DO_SPACE_NAME,
        region=settings.DO_REGION,
        access_key=settings.DO_ACCESS_KEY,
        secret_key=settings.DO_SECRET_KEY,
        key=latest_key,
        background_tasks=None,
    )
