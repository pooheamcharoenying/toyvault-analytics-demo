from fastapi import APIRouter, HTTPException
from typing import List
import pandas as pd
from pydantic import BaseModel

from app.utils import helper_functions as hf
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()

@router.get("/route", summary="Simple test route in app/api/routes")
def test_route():
    return {"message": "api/routes is wired correctly"}


# ---------- Schemas ----------
class BarcodesIn(BaseModel):
    barcodes: List[str]


def _get_barcode_lookup() -> pd.Series:
    """
    Build a barcode -> ItemCode lookup from the Item Master sheet
    of the main loaded Excel. This replaces the old Master NIC file
    dependency: the main Item Master has both 'Bar Code' and 'ItemCode'
    columns, so the same functionality works without a separate file.
    """
    if not hf.GLOBAL_DF or "master" not in hf.GLOBAL_DF:
        raise HTTPException(status_code=503, detail="Data not loaded yet")

    master = hf.GLOBAL_DF["master"]
    if "Bar Code" not in master.columns or "ItemCode" not in master.columns:
        raise HTTPException(
            status_code=500,
            detail="Item Master missing 'Bar Code' or 'ItemCode' column",
        )

    # Coerce to strings and drop empties before building the index
    subset = master[["Bar Code", "ItemCode"]].copy()
    subset["Bar Code"] = subset["Bar Code"].astype(str).str.strip()
    subset["ItemCode"] = subset["ItemCode"].astype(str).str.strip()
    subset = subset[(subset["Bar Code"] != "") & (subset["Bar Code"] != "nan")]
    subset = subset.drop_duplicates(subset=["Bar Code"], keep="first")
    return subset.set_index("Bar Code")["ItemCode"]


@router.post("/barcodes")
async def get_item_numbers(payload: BarcodesIn):
    """Look up ItemCodes for a list of barcodes, using the main Item Master."""
    barcode_list = payload.barcodes
    item_numbers: List[str | None] = []

    index_by_barcode = _get_barcode_lookup()

    for barcode in barcode_list:
        bc = str(barcode).strip()
        if bc in index_by_barcode.index:
            item_numbers.append(str(index_by_barcode[bc]))
        else:
            # Fallback: partial match (slower, rarely useful for EAN codes)
            hits = index_by_barcode.index[index_by_barcode.index.str.contains(bc, na=False)]
            if len(hits) > 0:
                item_numbers.append(str(index_by_barcode[hits[0]]))
            else:
                item_numbers.append(None)

    return {"item_numbers": item_numbers}
