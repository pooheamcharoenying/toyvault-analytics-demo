"""
Integration tests using REAL Excel data from the .excel_cache directory.

These tests catch bugs that mock-based tests miss — like column name mismatches
between real Excel data and code expectations. The Dscription→ItemName incident
(OBJ-59) is exactly the kind of bug these tests prevent.

Tests are SKIPPED if no Excel file is available (e.g., in CI without data).
To run locally: ensure .excel_cache/ has the Excel workbook.

Usage:
    cd "Nichiworld Railway App Backend"
    myenv/Scripts/python.exe -m unittest tests.test_real_data_integration -v
"""
from __future__ import annotations

import os
import sys
import glob
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

# --- Mock external dependencies (same as conftest.py) ---
import types

def _ensure_mock(module_name, attrs=None):
    try:
        __import__(module_name)
        return
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

_ensure_mock("pydantic", {"BaseModel": _FakeBaseModel})
_ensure_mock("pydantic_settings", {"BaseSettings": _FakeBaseSettings})
_ensure_mock("boto3")
_ensure_mock("sklearn")
_ensure_mock("sklearn.preprocessing")

import types as _t
fa = _t.ModuleType("fastapi")
fa.APIRouter = type("APIRouter", (), {"get": lambda *a, **kw: lambda f: f, "post": lambda *a, **kw: lambda f: f})
fa.FastAPI = type("FastAPI", (), {})
fa.Depends = lambda *a, **kw: None
fa.Query = lambda *a, **kw: None
fa.HTTPException = Exception
fa.Request = type("Request", (), {})

class _FakeJSONResponse:
    def __init__(self, content=None, **kw):
        self.content = content
        self.status_code = kw.get("status_code", 200)

fa.responses = _t.ModuleType("fastapi.responses")
fa.responses.JSONResponse = _FakeJSONResponse
sys.modules["fastapi"] = fa
sys.modules["fastapi.responses"] = fa.responses
sys.modules["fastapi.security"] = _t.ModuleType("fastapi.security")
sys.modules["fastapi.encoders"] = _t.ModuleType("fastapi.encoders")
sys.modules["fastapi.middleware"] = _t.ModuleType("fastapi.middleware")
sys.modules["fastapi.middleware.cors"] = _t.ModuleType("fastapi.middleware.cors")


# --- Locate Excel file ---
BACKEND_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BACKEND_DIR / ".excel_cache"

def _find_excel():
    """Find the most recent Excel file in .excel_cache/."""
    if not CACHE_DIR.exists():
        return None
    files = sorted(CACHE_DIR.glob("*.xlsx"), key=os.path.getmtime, reverse=True)
    return files[0] if files else None

EXCEL_PATH = _find_excel()
SKIP_REASON = "No Excel file in .excel_cache/ — run data server first to download"

# --- Sheet name mapping (matches app/main.py) ---
SHEET_MAP = {
    "Sale": "sale",
    "OnHand": "onhand",
    "Item Master": "master",
    "GRPO Detail": "grpo_detail",
    "Whs Code": "whs_code",
    "TR IN": "tr_in",
    "TR Out": "tr_out",
}


def _load_excel():
    """Load the Excel workbook into a dict matching GLOBAL_DF structure."""
    if EXCEL_PATH is None:
        return None
    data = {}
    for sheet_name, key in SHEET_MAP.items():
        try:
            df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
            data[key] = df
        except Exception:
            data[key] = pd.DataFrame()
    return data


# Cache so we only load once per test run
_CACHED_DATA = None

def _get_data():
    global _CACHED_DATA
    if _CACHED_DATA is None:
        _CACHED_DATA = _load_excel()
    return _CACHED_DATA


# ============================================================================
# TEST: Raw Excel Schema — Column names match what code expects
# ============================================================================

@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestRealExcelSchema(unittest.TestCase):
    """Verify that the real Excel file has the columns our code expects."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()

    def test_sale_has_required_columns(self):
        """Sale sheet must have the columns the pipeline depends on."""
        df = self.data["sale"]
        required = ["DocDate", "DocEntry", "ItemCode", "Quantity", "LineTotal",
                     "WhsCode", "GroupName"]
        for col in required:
            self.assertIn(col, df.columns, f"Sale sheet missing required column: {col}")

    def test_sale_has_dscription_not_itemname(self):
        """Sale sheet uses 'Dscription' (SAP spelling), NOT 'ItemName'.

        This is the EXACT test that would have caught the OBJ-59 bug.
        The raw data uses 'Dscription' — if someone renames it in code,
        this test fails.
        """
        df = self.data["sale"]
        self.assertIn("Dscription", df.columns,
                       "Sale sheet must have 'Dscription' column (SAP spelling). "
                       "If you renamed it, the production pipeline will break!")

    def test_item_master_has_required_columns(self):
        """Item Master must have GroupName (=Brand), ItemName, Price, ItemCode."""
        df = self.data["master"]
        required = ["ItemCode", "GroupName", "ItemName", "Price"]
        for col in required:
            self.assertIn(col, df.columns, f"Item Master missing: {col}")

    def test_item_master_groupname_is_brand(self):
        """Item Master GroupName contains brand names, not channel names."""
        df = self.data["master"]
        # GroupName should NOT contain typical channel names
        channel_names = {"Robinson", "CentralWorld", "Online", "Shopee", "Lazada"}
        actual_values = set(df["GroupName"].dropna().unique())
        overlap = actual_values & channel_names
        self.assertEqual(len(overlap), 0,
                          f"Item Master GroupName should be brands, but found channel names: {overlap}")

    def test_onhand_has_required_columns(self):
        """OnHand sheet must have ItemCode, OnHand, WhsCode."""
        df = self.data["onhand"]
        required = ["ItemCode", "OnHand", "WhsCode"]
        for col in required:
            self.assertIn(col, df.columns, f"OnHand missing: {col}")

    def test_whs_code_has_required_columns(self):
        """Whs Code sheet must have WhsCode and WhsName."""
        df = self.data["whs_code"]
        required = ["WhsCode", "WhsName"]
        for col in required:
            self.assertIn(col, df.columns, f"Whs Code missing: {col}")

    def test_grpo_has_required_columns(self):
        """GRPO Detail must have DocDate, ItemCode, Quantity, Price, Rate."""
        df = self.data["grpo_detail"]
        required = ["DocDate", "ItemCode", "Quantity", "Price", "Rate"]
        for col in required:
            self.assertIn(col, df.columns, f"GRPO Detail missing: {col}")

    def test_tr_in_has_required_columns(self):
        """TR IN must have DocDate, ItemCode, Quantity, WhsCode."""
        df = self.data["tr_in"]
        required = ["DocDate", "ItemCode", "Quantity", "WhsCode"]
        for col in required:
            self.assertIn(col, df.columns, f"TR IN missing: {col}")

    def test_tr_out_has_required_columns(self):
        """TR Out must have DocDate, ItemCode, Quantity, WhsCode."""
        df = self.data["tr_out"]
        required = ["DocDate", "ItemCode", "Quantity", "WhsCode"]
        for col in required:
            self.assertIn(col, df.columns, f"TR Out missing: {col}")

    def test_sale_row_count_is_substantial(self):
        """Sale sheet should have 100k+ rows (real data)."""
        df = self.data["sale"]
        self.assertGreater(len(df), 100000,
                            f"Sale sheet has only {len(df)} rows — expected 100k+ for real data")

    def test_item_master_row_count(self):
        """Item Master should have 1000+ items."""
        df = self.data["master"]
        self.assertGreater(len(df), 1000,
                            f"Item Master has only {len(df)} rows — expected 1000+")


# ============================================================================
# TEST: Data Pipeline — prepare_sales_and_onhand_data works with real data
# ============================================================================

@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestRealDataPipeline(unittest.TestCase):
    """Test that the core data pipeline works with real Excel data."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()
        from app.utils import nichi_stock as nstk
        cls.nstk = nstk

    def test_prepare_sales_and_onhand_data_succeeds(self):
        """The core pipeline function must not crash with real data."""
        df_sale, df_onhand, df_item_month = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        self.assertFalse(df_sale.empty, "Prepared sale data should not be empty")
        self.assertFalse(df_onhand.empty, "Prepared onhand data should not be empty")

    def test_prepared_sale_has_brand_column(self):
        """After preparation, sale data must have a Brand column (from master GroupName)."""
        df_sale, _, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        self.assertIn("Brand", df_sale.columns)
        # Most rows should have a brand
        non_null_pct = df_sale["Brand"].notna().mean()
        self.assertGreater(non_null_pct, 0.5,
                            f"Only {non_null_pct:.0%} of sale rows have Brand — expected >50%")

    def test_prepared_sale_has_itemname(self):
        """After preparation, sale data must have ItemName (renamed from Dscription)."""
        df_sale, _, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        self.assertIn("ItemName", df_sale.columns,
                       "Prepared sale data must have 'ItemName' column "
                       "(renamed from 'Dscription' at the data boundary)")

    def test_prepared_onhand_has_master_price(self):
        """After preparation, onhand data must have Master Price from item master."""
        _, df_onhand, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        self.assertIn("Master Price", df_onhand.columns)

    def test_channel_matrix_generation(self):
        """Channel matrix must produce a DataFrame with sales data."""
        df_sale, df_onhand, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        result = self.nstk.generate_sales_onhand_by_channel(df_sale, df_onhand)
        self.assertFalse(result.empty, "Channel matrix should not be empty")
        self.assertIn("Total", result.index, "Channel matrix must have a Total row")
        # Index should be named "Channel" (not raw "GroupName")
        self.assertEqual(result.index.name, "Channel",
                          f"Channel matrix index should be 'Channel', got '{result.index.name}'")

    def test_no_negative_revenue(self):
        """Total revenue should not be negative (sanity check)."""
        df_sale, _, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        total_revenue = df_sale["LineTotal"].sum()
        self.assertGreater(total_revenue, 0, "Total revenue must be positive")


# ============================================================================
# TEST: Stock Allocation with real data
# ============================================================================

@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestRealStockAllocation(unittest.TestCase):
    """Test stock allocation computation with real data."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()
        from app.utils import stock_allocation as sal
        cls.sal = sal

    def test_compute_stock_allocation_succeeds(self):
        """Stock allocation must not crash with real data."""
        result = self.sal.compute_stock_allocation(
            self.data["sale"], self.data["onhand"],
            self.data["master"], self.data["whs_code"],
            top_n=10,
        )
        self.assertIn("summary", result)
        self.assertIn("recommendations", result)
        self.assertIn("overstocked", result)
        self.assertIn("understocked", result)
        self.assertGreater(result["summary"]["total_items"], 0)

    def test_stock_allocation_has_itemname(self):
        """Transfer recommendations must include ItemName."""
        result = self.sal.compute_stock_allocation(
            self.data["sale"], self.data["onhand"],
            self.data["master"], self.data["whs_code"],
            top_n=5,
        )
        if result["recommendations"]:
            rec = result["recommendations"][0]
            self.assertIn("ItemName", rec,
                           "Transfer recommendations must include ItemName")

    def test_overstocked_has_itemname(self):
        """Overstocked records must include ItemName."""
        result = self.sal.compute_stock_allocation(
            self.data["sale"], self.data["onhand"],
            self.data["master"], self.data["whs_code"],
            top_n=5,
        )
        if result["overstocked"]:
            rec = result["overstocked"][0]
            self.assertIn("ItemName", rec,
                           "Overstocked records must include ItemName")

    def test_transfer_history_succeeds(self):
        """Transfer history must not crash with real data."""
        result = self.sal.compute_transfer_history(
            self.data["tr_in"], self.data["tr_out"],
            self.data["whs_code"], self.data["master"],
        )
        self.assertIn("summary", result)
        self.assertIn("location_flows", result)


# ============================================================================
# TEST: Executive helpers with real data
# ============================================================================

@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestRealExecutiveHelpers(unittest.TestCase):
    """Test executive dashboard computations with real data."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()
        from app.utils import nichi_stock as nstk
        from app.utils import executive_helpers as exh
        cls.nstk = nstk
        cls.exh = exh
        # Prepare data once (for tests that need prepared data)
        cls.df_sale, cls.df_onhand, cls.df_item_month = nstk.prepare_sales_and_onhand_data(
            cls.data["sale"], cls.data["onhand"], cls.data["master"]
        )

    def test_executive_summary_succeeds(self):
        """EX-01 executive summary must not crash with real data."""
        result = self.exh.compute_executive_summary(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        self.assertIn("totals", result)
        totals = result["totals"]
        self.assertIn("sold_thb", totals)
        self.assertIn("onhand_thb_master", totals)
        self.assertGreater(totals["sold_thb"], 0)
        self.assertGreater(totals["onhand_thb_master"], 0)

    def test_revenue_trend_succeeds(self):
        """EX-02 revenue trend must not crash with real data."""
        result = self.exh.compute_sales_trend_executive(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        self.assertIsInstance(result, dict)
        self.assertIn("series", result)
        self.assertGreater(len(result["series"]), 0)

    def test_revenue_values_are_sensible(self):
        """Revenue should be in the hundreds-of-millions THB range."""
        result = self.exh.compute_executive_summary(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        revenue = result["totals"]["sold_thb"]
        # Nichiworld does ~466M THB — should be > 100M
        self.assertGreater(revenue, 100_000_000,
                            f"Total revenue {revenue:,.0f} THB seems too low for real data")

    def test_onhand_value_is_sensible(self):
        """On-hand value should be in the tens-of-millions THB range."""
        result = self.exh.compute_executive_summary(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        onhand = result["totals"]["onhand_thb_master"]
        # Should be > 10M THB
        self.assertGreater(onhand, 10_000_000,
                            f"On-hand value {onhand:,.0f} THB seems too low for real data")


# ============================================================================
# TEST: Inventory Alerts with real data
# ============================================================================

@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestRealInventoryAlerts(unittest.TestCase):
    """Test inventory alert computations with real data."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()
        from app.utils import inventory_alerts as ia
        cls.ia = ia

    def test_stockout_risk_succeeds(self):
        """Stockout risk computation must not crash with real data."""
        result = self.ia.compute_stockout_risk(
            self.data["sale"], self.data["onhand"], self.data["master"],
        )
        self.assertIn("rows", result)
        self.assertIn("summary", result)

    def test_dead_stock_succeeds(self):
        """Dead stock computation must not crash with real data."""
        result = self.ia.compute_dead_stock(
            self.data["sale"], self.data["onhand"], self.data["master"],
        )
        self.assertIn("rows", result)

    def test_reorder_analysis_succeeds(self):
        """Reorder analysis must not crash with real data."""
        result = self.ia.compute_reorder_analysis(
            self.data["sale"], self.data["onhand"],
            self.data["master"], self.data["grpo_detail"],
        )
        self.assertIn("rows", result)


# ============================================================================
# TEST: Location Analytics with real data
# ============================================================================

@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestRealLocationAnalytics(unittest.TestCase):
    """Test location analytics computations with real data."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()
        from app.utils import location_analytics as la
        cls.la = la

    def test_location_performance_succeeds(self):
        """Location performance must not crash with real data."""
        result = self.la.compute_location_performance(
            self.data["sale"], self.data["onhand"],
            self.data["master"], self.data["whs_code"],
        )
        self.assertIn("locations", result)
        self.assertGreater(len(result["locations"]), 0,
                            "Should find at least 1 location")


# ============================================================================
# TEST: GP Commission integrity with real data
# ============================================================================

@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestRealGPCommission(unittest.TestCase):
    """Test GP commission calculations with real Excel data."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()
        from app.utils import nichi_stock as nstk
        cls.nstk = nstk

    def test_sale_has_u_act_gp_column(self):
        """Raw sale data must contain the U_ACT_GP column for GP commission."""
        self.assertIn("U_ACT_GP", self.data["sale"].columns,
                       "Sale sheet must have 'U_ACT_GP' column for GP commission")

    def test_sale_has_sale_type_column(self):
        """Raw sale data must contain Sale Type column (Consignment/Credit)."""
        self.assertIn("Sale Type", self.data["sale"].columns,
                       "Sale sheet must have 'Sale Type' column")

    def test_sale_type_values(self):
        """Sale Type should only have Consignment, Credit, or NaN."""
        valid_types = {"Consignment", "Credit"}
        actual_types = set(self.data["sale"]["Sale Type"].dropna().unique())
        unexpected = actual_types - valid_types
        self.assertEqual(len(unexpected), 0,
                          f"Unexpected Sale Type values: {unexpected}")

    def test_u_act_gp_range(self):
        """U_ACT_GP values should be percentages between 0 and 100."""
        gp = pd.to_numeric(self.data["sale"]["U_ACT_GP"], errors="coerce").dropna()
        if len(gp) > 0:
            self.assertGreaterEqual(gp.min(), 0,
                                     f"U_ACT_GP min={gp.min()}, expected >= 0")
            self.assertLessEqual(gp.max(), 100,
                                  f"U_ACT_GP max={gp.max()}, expected <= 100")

    def test_consignment_rows_have_gp(self):
        """Consignment sales should mostly have non-zero U_ACT_GP."""
        sale = self.data["sale"]
        consignment = sale[sale["Sale Type"] == "Consignment"]
        if len(consignment) > 0:
            gp = pd.to_numeric(consignment["U_ACT_GP"], errors="coerce").fillna(0)
            pct_with_gp = (gp > 0).mean()
            self.assertGreater(pct_with_gp, 0.9,
                                f"Only {pct_with_gp:.0%} of consignment rows have GP > 0, expected >90%")

    def test_credit_rows_have_no_gp(self):
        """Credit sales should have zero or null U_ACT_GP."""
        sale = self.data["sale"]
        credit = sale[sale["Sale Type"] == "Credit"]
        if len(credit) > 0:
            gp = pd.to_numeric(credit["U_ACT_GP"], errors="coerce").fillna(0)
            pct_zero = (gp == 0).mean()
            self.assertGreater(pct_zero, 0.95,
                                f"Only {pct_zero:.0%} of credit rows have GP=0, expected >95%")

    def test_compute_gp_commission_helper(self):
        """compute_gp_commission() must produce non-negative per-row values."""
        df_sale, _, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        gp = self.nstk.compute_gp_commission(df_sale)
        self.assertEqual(len(gp), len(df_sale),
                          "GP series must have same length as input")
        self.assertTrue((gp >= 0).all(),
                         "GP commission per row must be non-negative")
        # Total GP should be > 0 (consignment sales exist)
        total_gp = gp.sum()
        self.assertGreater(total_gp, 0,
                            f"Total GP commission should be > 0, got {total_gp}")

    def test_gp_less_than_revenue(self):
        """Total GP commission must be less than total revenue (sanity check)."""
        df_sale, _, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        gp_total = self.nstk.compute_gp_commission(df_sale).sum()
        revenue_total = df_sale["LineTotal"].sum()
        self.assertLess(gp_total, revenue_total,
                         f"GP commission ({gp_total:,.0f}) must be < revenue ({revenue_total:,.0f})")
        # GP should be a reasonable fraction of revenue (typically 10-40%)
        gp_pct = gp_total / revenue_total * 100
        self.assertGreater(gp_pct, 1,
                            f"GP commission is only {gp_pct:.1f}% of revenue — suspiciously low")
        self.assertLess(gp_pct, 50,
                         f"GP commission is {gp_pct:.1f}% of revenue — suspiciously high")

    def test_brand_profit_loss_includes_gp_columns(self):
        """Brand P/L output must include GP commission columns."""
        df_sale, df_onhand, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        # Pick a brand that has sales
        brands = df_sale["Brand"].dropna().value_counts()
        if len(brands) == 0:
            self.skipTest("No brands with sales found")
        top_brand = brands.index[0]

        result = self.nstk.generate_brand_product_profit_loss(
            df_sale, df_onhand, self.data["grpo_detail"], top_brand
        )
        self.assertFalse(result.empty)
        for col in ["GP_Commission_THB", "Net_Revenue_THB", "Profit_Loss_THB",
                     "Consignment_Revenue_THB", "Credit_Revenue_THB"]:
            self.assertIn(col, result.columns,
                           f"Brand P/L result must include '{col}' column")

        # TOTAL row should exist and have GP commission
        total_row = result[result["ItemCode"] == "TOTAL"]
        self.assertEqual(len(total_row), 1, "Must have exactly 1 TOTAL row")
        total_gp = total_row["GP_Commission_THB"].iloc[0]
        self.assertGreaterEqual(total_gp, 0, "Total GP commission must be >= 0")

    def test_profit_loss_formula_integrity(self):
        """P/L must equal Net Revenue − COGS for each item."""
        df_sale, df_onhand, _ = self.nstk.prepare_sales_and_onhand_data(
            self.data["sale"], self.data["onhand"], self.data["master"]
        )
        brands = df_sale["Brand"].dropna().value_counts()
        if len(brands) == 0:
            self.skipTest("No brands with sales found")
        top_brand = brands.index[0]

        result = self.nstk.generate_brand_product_profit_loss(
            df_sale, df_onhand, self.data["grpo_detail"], top_brand
        )
        # Check non-TOTAL rows
        items = result[result["ItemCode"] != "TOTAL"]
        for _, row in items.iterrows():
            expected_net = row["Actual_Revenue_THB"] - row["GP_Commission_THB"]
            self.assertAlmostEqual(
                row["Net_Revenue_THB"], expected_net, places=1,
                msg=f"Item {row['ItemCode']}: Net Revenue mismatch"
            )
            expected_pl = row["Net_Revenue_THB"] - row["Total_Cost_THB"]
            # P/L uses sold_qty * FOB, not Total_Cost (which is brought_qty * FOB)
            # So we check the formula: P/L = Actual Revenue - GP - (Sold_QTY * FOB)
            expected_pl2 = (row["Actual_Revenue_THB"] - row["GP_Commission_THB"]
                            - row["Sold_QTY"] * row["FOB_Price_THB"])
            self.assertAlmostEqual(
                row["Profit_Loss_THB"], expected_pl2, places=0,
                msg=f"Item {row['ItemCode']}: P/L formula mismatch"
            )


@unittest.skipIf(EXCEL_PATH is None, SKIP_REASON)
class TestOnlineChannelD1SL(unittest.TestCase):
    """Verify that the online warehouse D1-SL is included in all location analysis."""

    @classmethod
    def setUpClass(cls):
        cls.data = _get_data()

    def test_d1sl_exists_in_whs_code(self):
        """D1-SL should exist in the Whs Code sheet."""
        whs = self.data.get("whs_code")
        if whs is None or whs.empty:
            self.skipTest("No whs_code data")
        codes = whs["WhsCode"].astype(str).str.strip().tolist()
        self.assertIn("D1-SL", codes, "D1-SL not found in Whs Code sheet")

    def test_d1sl_has_onhand_records(self):
        """D1-SL should have on-hand inventory records."""
        oh = self.data.get("onhand")
        if oh is None or oh.empty:
            self.skipTest("No onhand data")
        d1sl_oh = oh[oh["WhsCode"].astype(str).str.strip() == "D1-SL"]
        self.assertGreater(len(d1sl_oh), 0, "D1-SL has no on-hand records")

    def test_d1sl_has_sales(self):
        """D1-SL should have sales transactions."""
        sale = self.data.get("sale")
        if sale is None or sale.empty:
            self.skipTest("No sale data")
        d1sl_sales = sale[sale["WhsCode"].astype(str).str.strip() == "D1-SL"]
        self.assertGreater(len(d1sl_sales), 0, "D1-SL has no sales transactions")

    def test_d1sl_in_location_performance(self):
        """D1-SL should appear in compute_location_performance output."""
        from app.utils import location_analytics as la
        from app.utils.location_consolidation import get_consolidated_name
        result = la.compute_location_performance(
            df_raw_sale=self.data["sale"],
            df_raw_onhand=self.data["onhand"],
            df_item_master=self.data["master"],
            df_whs_code=self.data["whs_code"],
        )
        loc_names = [loc["location"] for loc in result["locations"]]
        # D1-SL is consolidated to "Online (Shopee + Lazada)" via mapping
        whs = self.data["whs_code"]
        whs_lookup = dict(zip(
            whs["WhsCode"].astype(str).str.strip(),
            whs["WhsName"].astype(str),
        ))
        consolidated_name = get_consolidated_name("D1-SL", whs_lookup)
        d1sl_found = consolidated_name in loc_names or any(
            "Shopee" in n or "Online" in n for n in loc_names
        )
        self.assertTrue(d1sl_found,
                        f"D1-SL (consolidated: {consolidated_name}) not found in location performance. Locations: {loc_names[:20]}")

    def test_d1sl_has_positive_revenue(self):
        """D1-SL should have non-zero revenue in location performance."""
        from app.utils import location_analytics as la
        from app.utils.location_consolidation import get_consolidated_name
        result = la.compute_location_performance(
            df_raw_sale=self.data["sale"],
            df_raw_onhand=self.data["onhand"],
            df_item_master=self.data["master"],
            df_whs_code=self.data["whs_code"],
        )
        whs = self.data["whs_code"]
        whs_lookup = dict(zip(
            whs["WhsCode"].astype(str).str.strip(),
            whs["WhsName"].astype(str),
        ))
        consolidated_name = get_consolidated_name("D1-SL", whs_lookup)
        for loc in result["locations"]:
            if loc["location"] == consolidated_name or "Shopee" in loc["location"] or "Online" in loc["location"]:
                self.assertGreater(loc["sold_thb"], 0,
                                   f"D1-SL ({loc['location']}) has zero revenue")
                return
        self.fail(f"D1-SL ({consolidated_name}) not found in location performance output")


if __name__ == "__main__":
    unittest.main()
