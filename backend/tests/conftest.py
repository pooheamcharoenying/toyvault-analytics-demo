"""
Shared pytest fixtures and mock setup for testing without full FastAPI dependencies.

This conftest.py does two things:
1. Mocks external dependencies (FastAPI, pydantic, boto3, sklearn) so pure pandas
   logic in app/utils/ can be imported and tested without installing the full stack.
2. Provides realistic test fixtures at multiple sizes (small, medium) for thorough testing.
"""
from __future__ import annotations

import sys
import types
from datetime import date, datetime

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Mock external dependencies that the app.utils modules import at module level
# ---------------------------------------------------------------------------

def _ensure_mock(module_name, attrs=None):
    """Create a mock module if not already importable."""
    try:
        __import__(module_name)
        return  # Already available
    except ImportError:
        pass
    mod = types.ModuleType(module_name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[module_name] = mod


class _FakeBaseSettings:
    pass

class _FakeBaseModel:
    pass

class _FakeCryptContext:
    def __init__(self, **kw):
        pass
    def verify(self, *a):
        return True

class _FakeConfig:
    def __init__(self, **kw):
        pass

class _FakeLR:
    pass

# Only mock if not already installed
_ensure_mock("pydantic_settings", {"BaseSettings": _FakeBaseSettings})
_ensure_mock("pydantic", {"BaseModel": _FakeBaseModel})
_ensure_mock("passlib")
_ensure_mock("passlib.context", {"CryptContext": _FakeCryptContext})
_ensure_mock("boto3")
_ensure_mock("botocore")
_ensure_mock("botocore.client", {"Config": _FakeConfig})
_ensure_mock("sklearn")
_ensure_mock("sklearn.linear_model", {"LinearRegression": _FakeLR})

# FastAPI mock (only needed for module-level imports in helper_functions)
try:
    import fastapi
except ImportError:
    fa = types.ModuleType("fastapi")
    fa.BackgroundTasks = object
    fa.FastAPI = type("FastAPI", (), {"__init__": lambda self, **kw: None})
    fa.Depends = lambda x: x
    fa.File = None
    fa.UploadFile = None
    fa.HTTPException = Exception
    fa.status = types.ModuleType("fastapi.status")
    fa.status.HTTP_401_UNAUTHORIZED = 401
    fa.APIRouter = type("APIRouter", (), {"__init__": lambda self, **kw: None})
    sys.modules["fastapi"] = fa
    _fr = types.ModuleType("fastapi.responses")
    class _JSONResponse:
        def __init__(self, content=None, status_code=200, **kw):
            import json as _json
            self.status_code = status_code
            self.body = _json.dumps(content).encode() if content is not None else b"{}"
    _fr.JSONResponse = _JSONResponse
    sys.modules["fastapi.responses"] = _fr
    sys.modules["fastapi.security"] = types.ModuleType("fastapi.security")
    _fe = types.ModuleType("fastapi.encoders")
    _fe.jsonable_encoder = lambda obj, **kw: obj  # passthrough stub
    sys.modules["fastapi.encoders"] = _fe
    sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
    sys.modules["fastapi.middleware.cors"] = types.ModuleType("fastapi.middleware.cors")

# ---------------------------------------------------------------------------
# SMALL FIXTURES (2-5 rows per sheet — fast unit tests)
# ---------------------------------------------------------------------------

def _minimal_sale():
    return pd.DataFrame({
        "DocDate": pd.to_datetime(["2024-01-15", "2024-02-15"]),
        "DocEntry": [1, 2],
        "ItemCode": ["A1", "A1"],
        "ItemName": ["Item", "Item"],
        "Brand": [np.nan, "LineBrand"],
        "Price": [10.0, 10.0],
        "GroupName": ["Ch1", "Ch2"],
        "Quantity": [1, 2],
        "LineTotal": [100.0, 200.0],
        "WhsCode": ["WH01", "WH01"],
        "Master Price": [100.0, 100.0],
        "Price Master": [100.0, 200.0],  # Qty × unit master price
    })


def _minimal_onhand():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2"],
        "OnHand": [5, 3],
        "WhsCode": ["WH01", "WH01"],
    })


def _minimal_master():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2"],
        "GroupName": ["MasterBrand", "OtherBrand"],
        "ItemName": ["N1", "N2"],
        "Price": [100.0, 50.0],
    })


# ---------------------------------------------------------------------------
# MEDIUM FIXTURES (50+ rows — realistic data distributions)
# ---------------------------------------------------------------------------

_BRANDS = ["ToyWorld", "FunPlay", "KidZone", "BabyJoy", "SmartToy"]
_CHANNELS = ["Robinson", "CentralWorld", "OnlineShop"]
_WAREHOUSES = ["WH01", "WH02", "WH03", "WH04"]
_WHS_NAMES = ["Main Warehouse", "Bangkok Store", "Chiang Mai", "Phuket"]
_ITEMS_PER_BRAND = 5  # 25 items total


def _medium_master():
    """25 items across 5 brands with realistic attributes."""
    rows = []
    for bi, brand in enumerate(_BRANDS):
        for j in range(_ITEMS_PER_BRAND):
            item_code = f"{brand[:2].upper()}{j+1:03d}"
            rows.append({
                "ItemCode": item_code,
                "GroupName": brand,
                "ItemName": f"{brand} Product {j+1}",
                "Price": round(50.0 + bi * 30.0 + j * 10.0, 2),
                "LastPurPrc": round(30.0 + bi * 15.0 + j * 5.0, 2),
                "Brand": "",  # Often empty in real data
            })
    return pd.DataFrame(rows)


def _medium_onhand():
    """On-hand for 25 items across 4 warehouses (100 rows)."""
    rng = np.random.RandomState(42)
    master = _medium_master()
    rows = []
    for _, item in master.iterrows():
        for wh in _WAREHOUSES:
            qty = int(rng.poisson(lam=10))
            if qty > 0:  # Some items may have 0 at some locations
                rows.append({
                    "ItemCode": item["ItemCode"],
                    "OnHand": qty,
                    "WhsCode": wh,
                    "Price": item["Price"],
                    "SALETEAM": "TeamA",
                    "GroupName": "Shop",  # BP bucket — NOT product brand
                    "BP Code": "BP001",
                })
    # Add some items with zero stock
    rows.append({
        "ItemCode": "TO001", "OnHand": 0, "WhsCode": "WH01",
        "Price": 50.0, "SALETEAM": "TeamA", "GroupName": "Shop", "BP Code": "BP001",
    })
    return pd.DataFrame(rows)


def _medium_sale():
    """200+ sale lines across 2 years, 5 brands, 3 channels, 4 warehouses."""
    rng = np.random.RandomState(42)
    master = _medium_master()
    items = master["ItemCode"].tolist()
    brands = master.set_index("ItemCode")["GroupName"].to_dict()
    prices = master.set_index("ItemCode")["Price"].to_dict()

    rows = []
    doc_entry = 1000
    # Generate sales from 2023-01 through 2025-03 (26 months)
    for year in [2023, 2024, 2025]:
        months = range(1, 13) if year < 2025 else range(1, 4)
        for month in months:
            n_sales = rng.randint(5, 15)
            for _ in range(n_sales):
                item = rng.choice(items)
                channel = rng.choice(_CHANNELS)
                wh = rng.choice(_WAREHOUSES)
                qty = int(rng.randint(1, 20))
                price = prices.get(item, 100.0)
                day = rng.randint(1, 28)
                rows.append({
                    "DocDate": pd.Timestamp(year, month, day),
                    "DocEntry": doc_entry,
                    "ItemCode": item,
                    "ItemName": f"Desc {item}",
                    "Brand": brands.get(item) if rng.random() > 0.3 else np.nan,  # 30% missing
                    "Price": price,
                    "GroupName": channel,
                    "Quantity": qty,
                    "LineTotal": round(qty * price * rng.uniform(0.8, 1.2), 2),
                    "WhsCode": wh,
                    "Master Price": price,
                    "Price Master": round(qty * price, 2),
                })
                doc_entry += 1

    # Add some duplicate lines (same DocEntry+ItemCode+Period+GroupName)
    if len(rows) > 10:
        dup1 = rows[5].copy()
        dup2 = rows[10].copy()
        rows.extend([dup1, dup2])

    return pd.DataFrame(rows)


def _medium_grpo():
    """GRPO (purchase) lines for medium fixture — 80+ rows across items and warehouses."""
    rng = np.random.RandomState(123)
    master = _medium_master()
    items = master["ItemCode"].tolist()

    rows = []
    doc_entry = 5000
    for year in [2023, 2024, 2025]:
        months = range(1, 13) if year < 2025 else range(1, 4)
        for month in months:
            n_purchases = rng.randint(2, 6)
            for _ in range(n_purchases):
                item = rng.choice(items)
                qty = int(rng.randint(10, 100))
                price_usd = round(rng.uniform(1.0, 20.0), 2)
                rate = round(rng.uniform(33.0, 36.0), 4)
                rows.append({
                    "DocDate": pd.Timestamp(year, month, rng.randint(1, 28)),
                    "DocEntry": doc_entry,
                    "ItemCode": item,
                    "ItemName": f"Purchase {item}",
                    "Quantity": qty,
                    "Price": price_usd,
                    "Currency": "USD",
                    "Rate": rate,
                    "LineTotal": round(qty * price_usd, 2),
                    "WhsCode": rng.choice(_WAREHOUSES),
                    "CardCode": "V001",
                    "CardName": "Vendor Co",
                    "ShipDate": pd.Timestamp(year, month, rng.randint(1, 28)),
                    "TargetType": "",
                    "TrgetEntry": "",
                    "BaseType": "",
                    "BaseEntry": "",
                    "BaseRef": "",
                    "LineNum": 0,
                })
                doc_entry += 1

    return pd.DataFrame(rows)


def _medium_tr_in():
    """Transfer IN lines — items moving into warehouses."""
    rng = np.random.RandomState(200)
    master = _medium_master()
    items = master["ItemCode"].tolist()

    rows = []
    doc_entry = 8000
    for year in [2024, 2025]:
        months = range(1, 13) if year < 2025 else range(1, 4)
        for month in months:
            n_transfers = rng.randint(1, 4)
            for _ in range(n_transfers):
                item = rng.choice(items)
                rows.append({
                    "DocEntry": doc_entry,
                    "DocDate": pd.Timestamp(year, month, rng.randint(1, 28)),
                    "ShipDate": pd.Timestamp(year, month, rng.randint(1, 28)),
                    "LineNum": 0,
                    "CodeBars": "",
                    "ItemCode": item,
                    "ItemName": f"TR IN {item}",
                    "Quantity": int(rng.randint(1, 30)),
                    "WhsCode": rng.choice(_WAREHOUSES),
                })
                doc_entry += 1

    return pd.DataFrame(rows)


def _medium_tr_out():
    """Transfer OUT lines — items leaving warehouses (NEGATIVE quantities)."""
    rng = np.random.RandomState(300)
    master = _medium_master()
    items = master["ItemCode"].tolist()

    rows = []
    doc_entry = 9000
    for year in [2024, 2025]:
        months = range(1, 13) if year < 2025 else range(1, 4)
        for month in months:
            n_transfers = rng.randint(1, 4)
            for _ in range(n_transfers):
                item = rng.choice(items)
                rows.append({
                    "DocEntry": doc_entry,
                    "DocDate": pd.Timestamp(year, month, rng.randint(1, 28)),
                    "ShipDate": pd.Timestamp(year, month, rng.randint(1, 28)),
                    "LineNum": 0,
                    "CodeBars": "",
                    "ItemCode": item,
                    "ItemName": f"TR OUT {item}",
                    "Quantity": -int(rng.randint(1, 30)),  # NEGATIVE for outbound
                    "WhsCode": rng.choice(_WAREHOUSES),
                })
                doc_entry += 1

    return pd.DataFrame(rows)


def _medium_whs_code():
    """Warehouse code to name mapping."""
    return pd.DataFrame({
        "WhsCode": _WAREHOUSES,
        "WhsName": _WHS_NAMES,
    })
