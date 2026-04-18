"""Tests for home_summary period comparison logic (OBJ-33 regression)."""
from __future__ import annotations
import unittest
import tests.conftest  # noqa: F401 — must be imported first to set up mocks

import pandas as pd
from app.utils.nichi_stock import prepare_sales_and_onhand_data


class TestHomeSummaryPeriodComparison(unittest.TestCase):
    """Regression tests for the tuple/dict mismatch bug in home_summary."""

    def _make_fixtures(self):
        """Create test DataFrames with multi-year sales data."""
        df_sale = pd.DataFrame({
            "DocEntry": [1, 2, 3, 4],
            "ItemCode": ["A001", "A001", "A002", "A002"],
            "DocDate": ["2024-03-15", "2024-06-10", "2025-03-05", "2025-06-20"],
            "WhsCode": ["WH01", "WH01", "WH01", "WH01"],
            "Quantity": [10, 20, 30, 40],
            "LineTotal": [1000, 2000, 3000, 4000],
            "GroupName": ["Shop", "Shop", "Shop", "Shop"],
            "Brand": [None, None, None, None],
            "ItemName": ["Widget", "Widget", "Gadget", "Gadget"],
            "Price": [100.0, 100.0, 100.0, 100.0],
        })
        df_onhand = pd.DataFrame({
            "ItemCode": ["A001", "A002"],
            "WhsCode": ["WH01", "WH01"],
            "OnHand": [50, 100],
            "GroupName": ["Shop", "Shop"],
        })
        df_master = pd.DataFrame({
            "ItemCode": ["A001", "A002"],
            "ItemName": ["Widget", "Gadget"],
            "GroupName": ["BrandA", "BrandB"],
            "Price": [100.0, 100.0],
        })
        return df_sale, df_onhand, df_master

    def test_prepare_returns_tuple_not_dict(self):
        """prepare_sales_and_onhand_data must return a tuple of 3 DataFrames."""
        df_sale, df_onhand, df_master = self._make_fixtures()
        result = prepare_sales_and_onhand_data(df_sale.copy(), df_onhand.copy(), df_master.copy())
        self.assertIsInstance(result, tuple, "Must return a tuple, not a dict")
        self.assertEqual(len(result), 3, "Must return exactly 3 elements")
        self.assertIsInstance(result[0], pd.DataFrame, "First element must be df_sale")
        self.assertIsInstance(result[1], pd.DataFrame, "Second element must be df_onhand")
        self.assertIsInstance(result[2], pd.DataFrame, "Third element must be df_item_month")

    def test_enriched_sale_has_brand_column(self):
        """The enriched df_sale should have Brand filled from Item Master."""
        df_sale, df_onhand, df_master = self._make_fixtures()
        df_s, _, _ = prepare_sales_and_onhand_data(df_sale.copy(), df_onhand.copy(), df_master.copy())
        self.assertIn("Brand", df_s.columns, "Enriched sale must have Brand column")
        # Brand should be filled from Item Master GroupName
        brands = df_s["Brand"].dropna().unique()
        self.assertTrue(len(brands) > 0, "At least some rows should have Brand filled")

    def test_yoy_calculation_uses_enriched_data(self):
        """Reproduce the home_summary YoY calculation with enriched data (not raw)."""
        df_sale, df_onhand, df_master = self._make_fixtures()
        # This is what the fixed code does:
        df_s, _, _ = prepare_sales_and_onhand_data(df_sale.copy(), df_onhand.copy(), df_master.copy())

        df_s["DocDate"] = pd.to_datetime(df_s["DocDate"], errors="coerce")
        df_s["_year"] = df_s["DocDate"].dt.year
        years = sorted(df_s["_year"].dropna().unique())
        self.assertEqual(len(years), 2, "Should have 2 years of data")
        self.assertEqual(years, [2024, 2025])

        rev_2024 = df_s.loc[df_s["_year"] == 2024, "LineTotal"].sum()
        rev_2025 = df_s.loc[df_s["_year"] == 2025, "LineTotal"].sum()
        self.assertEqual(rev_2024, 3000)
        self.assertEqual(rev_2025, 7000)

        yoy_pct = (rev_2025 - rev_2024) / rev_2024 * 100
        self.assertAlmostEqual(yoy_pct, 133.3, places=1)

    def test_tuple_unpacking_does_not_raise(self):
        """Tuple unpacking via df_s, _, _ = ... must not raise."""
        df_sale, df_onhand, df_master = self._make_fixtures()
        try:
            df_s, _, _ = prepare_sales_and_onhand_data(
                df_sale.copy(), df_onhand.copy(), df_master.copy()
            )
        except (TypeError, ValueError) as e:
            self.fail(f"Tuple unpacking raised {type(e).__name__}: {e}")
        self.assertFalse(df_s.empty)


if __name__ == "__main__":
    unittest.main()
