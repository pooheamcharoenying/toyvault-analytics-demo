"""
Iteration 11: API Contract Tests.

Tests ensure:
1. All output DataFrames use orient="split" compatible structure (columns, index, data)
2. Column naming conventions are consistent ({date}_{Metric})
3. Index is always meaningful (brand name, item code, channel name)
4. Total row is present where expected
5. Return types and shapes are correct
"""
from __future__ import annotations

import sys
import os
import unittest
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as fixtures

from app.utils.nichi_stock import (
    prepare_sales_and_onhand_data,
    generate_sales_onhand_by_channel,
    generate_sales_onhand_by_brand,
    generate_sales_onhand_by_brand_channel,
)
from app.utils.product_sale_onhand import (
    generate_product_sale_vs_onhand,
    generate_product_sale_vs_onhand_locations,
)
from app.utils.executive_helpers import (
    compute_executive_summary,
    compute_margin_by_brand,
    compute_inventory_risk_summary,
    compute_concentration_summary,
    compute_sales_trend_executive,
)


def _raw():
    return fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()


class TestDataFrameContracts(unittest.TestCase):
    """Tests that DataFrame outputs can be serialized with orient='split'."""

    def _assert_split_compatible(self, df, name):
        """DataFrame should produce valid orient='split' dict."""
        self.assertIsInstance(df, pd.DataFrame, f"{name} should be DataFrame")
        self.assertFalse(df.empty, f"{name} should not be empty")

        # to_dict(orient='split') should work without error
        result = df.to_dict(orient='split')
        self.assertIn('columns', result)
        self.assertIn('index', result)
        self.assertIn('data', result)
        self.assertEqual(len(result['data']), len(df))
        if len(result['data']) > 0:
            self.assertEqual(len(result['data'][0]), len(result['columns']))

    def test_channel_matrix_split(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        self._assert_split_compatible(result, "channel_matrix")

    def test_brand_matrix_split(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        self._assert_split_compatible(result, "brand_matrix")

    def test_brand_channel_matrix_split(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand_channel(
            df_sale, df_onhand, brand_name="ToyWorld",
            period_type="monthly", year_list=[2024, 2025]
        )
        if not result.empty:
            self._assert_split_compatible(result, "brand_channel_matrix")

    def test_product_sale_onhand_split(self):
        sale, onhand, master = _raw()
        result = generate_product_sale_vs_onhand(
            df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            brand_name="ToyWorld", file_date=date(2025, 3, 15),
        )
        self._assert_split_compatible(result, "product_sale_onhand")

    def test_product_sale_onhand_locations_split(self):
        sale, onhand, master = _raw()
        result = generate_product_sale_vs_onhand_locations(
            df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            df_whs_code=fixtures._medium_whs_code(),
            brand_name="ToyWorld", file_date=date(2025, 3, 15),
        )
        self._assert_split_compatible(result, "product_sale_onhand_locations")


class TestColumnNamingConventions(unittest.TestCase):
    """Tests that column names follow the {date}_{Metric} convention."""

    def test_channel_columns_follow_convention(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)

        for col in result.columns:
            parts = col.split("_", 1)
            self.assertEqual(len(parts), 2,
                f"Column '{col}' should have format 'date_metric'")
            date_part, metric_part = parts
            # Date should be YYYY-MM-DD
            self.assertRegex(date_part, r'^\d{4}-\d{2}-\d{2}$',
                f"Date part '{date_part}' should be YYYY-MM-DD")
            self.assertIn(metric_part, ["Sold_QTY", "Sold_THB", "OnHand_QTY", "OnHand_THB"],
                f"Metric '{metric_part}' should be recognized")

    def test_brand_columns_follow_convention(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)

        for col in result.columns:
            parts = col.split("_", 1)
            self.assertEqual(len(parts), 2,
                f"Column '{col}' should have format 'date_metric'")


class TestTotalRowPresence(unittest.TestCase):
    """Tests that Total row is present in all matrix-style outputs."""

    def test_channel_has_total(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        self.assertIn("Total", result.index)

    def test_brand_has_total(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        self.assertIn("Total", result.index)

    def test_pso_has_total(self):
        sale, onhand, master = _raw()
        result = generate_product_sale_vs_onhand(
            df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            brand_name="ToyWorld", file_date=date(2025, 3, 15),
        )
        self.assertIn("Total", result.index)


class TestExecutiveAPIContracts(unittest.TestCase):
    """Tests for executive helper return types."""

    def test_executive_summary_structure(self):
        sale, onhand, master = _raw()
        result = compute_executive_summary(sale, onhand, master)
        self.assertIsInstance(result, dict)
        self.assertIn("totals", result)
        for key in ["sold_qty", "sold_thb", "onhand_qty", "onhand_thb_master"]:
            self.assertIn(key, result["totals"])
            self.assertIsInstance(result["totals"][key], float)

    def test_margin_structure(self):
        sale, onhand, master = _raw()
        result = compute_margin_by_brand(sale, onhand, master)
        self.assertIsInstance(result, dict)
        self.assertIn("rows", result)
        self.assertIn("totals", result)
        for row in result["rows"]:
            for key in ["brand", "revenue_thb", "cogs_thb", "gross_margin_thb"]:
                self.assertIn(key, row)

    def test_concentration_structure(self):
        sale, onhand, master = _raw()
        result = compute_concentration_summary(sale, onhand, master, "brand", 2024)
        self.assertIsInstance(result, dict)
        self.assertIn("rows", result)
        self.assertIn("top_k_share_pct", result)
        for row in result["rows"]:
            for key in ["name", "revenue_thb", "share_pct"]:
                self.assertIn(key, row)

    def test_trend_structure(self):
        sale, onhand, master = _raw()
        result = compute_sales_trend_executive(sale, onhand, master)
        self.assertIsInstance(result, dict)
        self.assertIn("series", result)
        for entry in result["series"]:
            for key in ["period", "revenue_thb", "qty"]:
                self.assertIn(key, entry)

    def test_risk_structure(self):
        sale, onhand, master = _raw()
        result = compute_inventory_risk_summary(sale, onhand, master)
        self.assertIsInstance(result, dict)
        self.assertIn("rows", result)
        for row in result["rows"]:
            for key in ["item_code", "onhand_qty", "days_cover"]:
                self.assertIn(key, row)


if __name__ == "__main__":
    unittest.main()
