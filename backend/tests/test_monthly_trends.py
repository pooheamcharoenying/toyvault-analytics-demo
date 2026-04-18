"""Tests for monthly trend functions (OBJ-81).

Tests:
- compute_brand_monthly_trend() — brand-level monthly revenue/cost/margin
- compute_item_monthly_trend() — item-level monthly sales
- compute_brand_at_location_trend() — brand at location monthly revenue
"""
from __future__ import annotations
import unittest
import tests.conftest  # noqa: F401

import numpy as np
import pandas as pd
from app.utils.executive_helpers import compute_brand_monthly_trend
from app.utils.item_detail import compute_item_monthly_trend
from app.utils.location_analytics import compute_brand_at_location_trend


def _make_sale_fixture():
    """Create sales data spanning 3 months, 2 brands, 2 locations.

    Must include all columns expected by prepare_sales_and_onhand_data:
    DocDate, DocEntry, ItemCode, ItemName, Brand, Price, GroupName, Quantity,
    LineTotal, WhsCode, Master Price, Price Master, U_ACT_GP, Sale Type.
    """
    return pd.DataFrame({
        "DocEntry": [1, 2, 3, 4, 5, 6, 7, 8],
        "ItemCode": ["A1", "A1", "A2", "B1", "A1", "B1", "A1", "B1"],
        "ItemName": ["W1", "W1", "W2", "G1", "W1", "G1", "W1", "G1"],
        "DocDate": pd.to_datetime([
            "2024-01-15", "2024-02-10", "2024-01-20",
            "2024-01-15", "2024-03-05", "2024-02-20",
            "2024-01-25", "2024-03-10",
        ]),
        "WhsCode": ["WH01", "WH01", "WH01", "WH02", "WH01", "WH02", "WH02", "WH01"],
        "Quantity": [10, 20, 5, 8, 15, 12, 7, 3],
        "LineTotal": [1000, 2000, 500, 400, 1500, 600, 700, 150],
        "GroupName": ["Shop", "Shop", "Shop", "Online", "Shop", "Online", "Online", "Shop"],
        "Brand": ["BrandA", "BrandA", "BrandA", "BrandB", "BrandA", "BrandB", "BrandA", "BrandB"],
        "Price": [100.0, 100.0, 100.0, 50.0, 100.0, 50.0, 100.0, 50.0],
        "Master Price": [100.0, 100.0, 100.0, 50.0, 100.0, 50.0, 100.0, 50.0],
        "Price Master": [1000, 2000, 500, 400, 1500, 600, 700, 150],  # Qty × unit master price
        "U_ACT_GP": [0, 0, 0, 0, 0, 0, 0, 0],
        "Sale Type": ["Credit"] * 8,
    })


def _make_master_fixture():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1"],
        "ItemName": ["Widget A1", "Widget A2", "Gadget B1"],
        "GroupName": ["BrandA", "BrandA", "BrandB"],
        "Price": [100.0, 100.0, 50.0],
        "LastPurPrc": [40.0, 40.0, 20.0],
    })


def _make_onhand_fixture():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1"],
        "WhsCode": ["WH01", "WH01", "WH02"],
        "OnHand": [50, 30, 100],
    })


def _make_whs_fixture():
    return pd.DataFrame({
        "WhsCode": ["WH01", "WH02"],
        "WhsName": ["Main Warehouse", "Shop Downtown"],
    })


class TestBrandMonthlyTrend(unittest.TestCase):
    """Tests for compute_brand_monthly_trend()."""

    def test_top_n_brands(self):
        """Returns top N brands with monthly data."""
        result = compute_brand_monthly_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            top_n=2, year_list=[2024],
        )
        self.assertIn("trends", result)
        self.assertIn("periods", result)
        self.assertGreater(len(result["trends"]), 0)
        self.assertLessEqual(len(result["trends"]), 2)

    def test_single_brand(self):
        """Returns a single brand when brand_name is specified."""
        result = compute_brand_monthly_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            brand_name="BrandA", year_list=[2024],
        )
        self.assertEqual(len(result["trends"]), 1)
        self.assertEqual(result["trends"][0]["brand"], "BrandA")

    def test_monthly_fields(self):
        """Each month has required metric fields."""
        result = compute_brand_monthly_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            brand_name="BrandA", year_list=[2024],
        )
        months = result["trends"][0]["months"]
        self.assertGreater(len(months), 0)
        for m in months:
            self.assertIn("period", m)
            self.assertIn("sold_thb", m)
            self.assertIn("sold_master_thb", m)
            self.assertIn("sold_qty", m)
            self.assertIn("cogs_thb", m)
            self.assertIn("profit_loss", m)

    def test_year_filter(self):
        """Year filter excludes data from other years."""
        result = compute_brand_monthly_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            year_list=[2025],  # no data in 2025
        )
        self.assertEqual(len(result["trends"]), 0)

    def test_periods_sorted(self):
        """Periods are in chronological order."""
        result = compute_brand_monthly_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            year_list=[2024],
        )
        periods = result["periods"]
        self.assertEqual(periods, sorted(periods))


class TestItemMonthlyTrend(unittest.TestCase):
    """Tests for compute_item_monthly_trend()."""

    def test_basic_structure(self):
        """Returns found=True and months list."""
        result = compute_item_monthly_trend(
            "A1", _make_sale_fixture(), _make_master_fixture(), year_list=[2024],
        )
        self.assertTrue(result["found"])
        self.assertIn("months", result)
        self.assertGreater(len(result["months"]), 0)

    def test_monthly_fields(self):
        """Each month has required fields."""
        result = compute_item_monthly_trend(
            "A1", _make_sale_fixture(), _make_master_fixture(), year_list=[2024],
        )
        for m in result["months"]:
            self.assertIn("period", m)
            self.assertIn("sold_qty", m)
            self.assertIn("sold_thb", m)
            self.assertIn("sold_master_thb", m)

    def test_master_revenue_calculation(self):
        """sold_master_thb should equal sold_qty × master_price."""
        result = compute_item_monthly_trend(
            "A1", _make_sale_fixture(), _make_master_fixture(), year_list=[2024],
        )
        for m in result["months"]:
            expected_master = m["sold_qty"] * 100.0  # master price = 100
            self.assertAlmostEqual(m["sold_master_thb"], expected_master, places=0)

    def test_nonexistent_item(self):
        """Returns found=False for nonexistent item."""
        result = compute_item_monthly_trend(
            "NONEXIST", _make_sale_fixture(), _make_master_fixture(),
        )
        self.assertFalse(result["found"])

    def test_year_filter(self):
        """Year filter excludes data from other years."""
        result = compute_item_monthly_trend(
            "A1", _make_sale_fixture(), _make_master_fixture(), year_list=[2025],
        )
        self.assertTrue(result["found"])
        self.assertEqual(len(result["months"]), 0)


class TestBrandAtLocationTrend(unittest.TestCase):
    """Tests for compute_brand_at_location_trend()."""

    def test_basic_structure(self):
        """Returns months list."""
        result = compute_brand_at_location_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            _make_whs_fixture(),
            location="Main Warehouse", brand="BrandA", year_list=[2024],
        )
        self.assertIn("months", result)
        self.assertGreater(len(result["months"]), 0)

    def test_monthly_fields(self):
        """Each month has required fields."""
        result = compute_brand_at_location_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            _make_whs_fixture(),
            location="Main Warehouse", brand="BrandA", year_list=[2024],
        )
        for m in result["months"]:
            self.assertIn("period", m)
            self.assertIn("sold_thb", m)
            self.assertIn("sold_master_thb", m)
            self.assertIn("sold_qty", m)

    def test_nonexistent_location(self):
        """Returns empty months for nonexistent location."""
        result = compute_brand_at_location_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            _make_whs_fixture(),
            location="NONEXIST", brand="BrandA",
        )
        self.assertEqual(len(result["months"]), 0)

    def test_nonexistent_brand(self):
        """Returns empty months for nonexistent brand."""
        result = compute_brand_at_location_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            _make_whs_fixture(),
            location="Main Warehouse", brand="NONEXIST",
        )
        self.assertEqual(len(result["months"]), 0)

    def test_year_filter(self):
        """Year filter works."""
        result = compute_brand_at_location_trend(
            _make_sale_fixture(), _make_onhand_fixture(), _make_master_fixture(),
            _make_whs_fixture(),
            location="Main Warehouse", brand="BrandA", year_list=[2025],
        )
        self.assertEqual(len(result["months"]), 0)


if __name__ == "__main__":
    unittest.main()
