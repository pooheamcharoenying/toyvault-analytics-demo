from fastapi import APIRouter
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

# Read once per request (consider caching if the file is large/unchanged)
master_nic = pd.read_excel(
    "app/Master NIC 11-09-25 UP.xlsx",
    sheet_name="Master SAP 11-09-25",
    engine="openpyxl",
    dtype={"Bar Code": str, "Item No.": str},
)

@router.post("/barcodes")
async def get_item_numbers(payload: BarcodesIn):
    barcode_list = payload.barcodes
    item_numbers: List[str] = []

    # Build a fast lookup (exact match). If you truly need partial matches, switch back to .str.contains.
    master_nic_drop = master_nic.dropna(subset=["Bar Code", "Item No."])
    index_by_barcode = master_nic_drop.set_index("Bar Code")["Item No."]

    for barcode in barcode_list:
        bc = str(barcode)
        if bc in index_by_barcode:
            item_numbers.append(index_by_barcode[bc])
        else:
            # Fallback to contains (slow) only if exact not found — optional
            matches = master_nic[master_nic["Bar Code"].str.contains(bc, na=False)]
            if not matches.empty:
                item_numbers.append(matches.iloc[0]["Item No."])
            else:
                item_numbers.append(None)  # or raise an HTTPException

    return {"item_numbers": item_numbers}
