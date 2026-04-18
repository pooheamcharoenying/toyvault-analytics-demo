"""Shared helpers for analytics API routes: DataFrame → JSON split response."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi.responses import JSONResponse


def dataframe_split_json_response(df: pd.DataFrame) -> JSONResponse:
    """Serialize a DataFrame as orient='split' JSON (columns, index, data) for frontend tables."""
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = ["|".join(map(str, col)) for col in out.columns.values]
    else:
        out.columns = [str(c) for c in out.columns]
    out = out.replace([np.inf, -np.inf], np.nan)
    return JSONResponse(
        content=out.to_json(orient="split", date_format="iso"),
        media_type="application/json",
    )
