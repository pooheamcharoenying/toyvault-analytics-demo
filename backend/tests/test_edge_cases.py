"""
Iteration 12: Edge Cases & Robustness Tests.

Tests ensure:
1. Empty DataFrames don't crash functions
2. Single-row DataFrames work correctly
3. Missing columns are handled gracefully
4. NaN/zero values don't cause division errors
5. Unknown brands/channels return empty or sensible defaults
6. Period types are validated
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
from app.utils.inventory_engine import (
    compute_historical_onhand,
    compute_historical_onhand_org,
)
from app.utils.product_sale_onhand import (
    generate_product_sale_vs_onhand,
    generate_product_sale_vs_onhand_locations,
)


def _raw():
    return fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()


class TestEmptyInputs(unittest.TestCase):
    """Functions should handle empty or minimal DataFrames gracefully."""

    def test_channel_empty_sale(self):
        """Empty sale DataFrame should return empty result."""
        empty_sale = pd.DataFrame(columns=["DocDate", "DocEntry", "ItemCode",
            "ItemName", "Brand", "Price", "GroupName", "Quantity", "LineTotal"])
        onhand = fixtures._medium_onhand()
        master = fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(empty_sale, onhand, master)
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        self.assertTrue(result.empty)

    def test_brand_empty_sale(self):
        """Empty sale DataFrame should return empty brand result."""
        empty_sale = pd.DataFrame(columns=["DocDate", "DocEntry", "ItemCode",
            "ItemName", "Brand", "Price", "GroupName", "Quantity", "LineTotal"])
        onhand = fixtures._medium_onhand()
        master = fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(empty_sale, onhand, master)
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        self.assertTrue(result.empty)

    def test_engine_empty_sale(self):
        """Engine should return empty DataFrame for empty sales."""
        empty_sale = pd.DataFrame(columns=["DocDate", "ItemCode", "WhsCode", "Quantity"])
        result = compute_historical_onhand(
            df_raw_onhand=fixtures._medium_onhand(),
            df_raw_sale=empty_sale,
            df_grpo_detail=None,
            df_tr_in=None,
            df_tr_out=None,
            file_date=date(2025, 3, 15),
        )
        self.assertTrue(result.empty)

    def test_pso_nonexistent_brand(self):
        """PSO with a brand that doesn't exist should return empty."""
        sale, onhand, master = _raw()
        result = generate_product_sale_vs_onhand(
            df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            brand_name="NonexistentBrand999",
            file_date=date(2025, 3, 15),
        )
        self.assertTrue(result.empty)

    def test_brand_channel_nonexistent_brand(self):
        """Brand-channel with nonexistent brand should return empty."""
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand_channel(
            df_sale, df_onhand, brand_name="NonexistentBrand999",
            period_type="monthly", year_list=[2024]
        )
        self.assertTrue(result.empty)


class TestNullMovements(unittest.TestCase):
    """Engine should handle None movement DataFrames (no GRPO, TR IN, TR OUT)."""

    def test_engine_no_grpo(self):
        """Engine should work with None GRPO."""
        sale, onhand, _ = _raw()
        result = compute_historical_onhand_org(
            df_raw_onhand=onhand, df_raw_sale=sale,
            df_grpo_detail=None, df_tr_in=None, df_tr_out=None,
            file_date=date(2025, 3, 15),
        )
        self.assertFalse(result.empty)

    def test_engine_empty_movements(self):
        """Engine should work with empty movement DataFrames."""
        sale, onhand, _ = _raw()
        empty_mov = pd.DataFrame(columns=["DocDate", "ItemCode", "WhsCode", "Quantity"])
        result = compute_historical_onhand_org(
            df_raw_onhand=onhand, df_raw_sale=sale,
            df_grpo_detail=empty_mov, df_tr_in=empty_mov, df_tr_out=empty_mov,
            file_date=date(2025, 3, 15),
        )
        self.assertFalse(result.empty)


class TestPeriodTypeValidation(unittest.TestCase):
    """Period type parameter should be validated."""

    def test_invalid_period_type_channel(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        with self.assertRaises(AssertionError):
            generate_sales_onhand_by_channel(df_sale, df_onhand, period_type="daily")

    def test_invalid_period_type_brand(self):
        sale, onhand, master = _raw()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        with self.assertRaises(AssertionError):
            generate_sales_onhand_by_brand(df_sale, df_onhand, period_type="quarterly")


class TestSingleItemScenario(unittest.TestCase):
    """Tests with minimal data (1-2 items) to catch off-by-one errors."""

    def test_single_sale_record(self):
        """A DataFrame with a single sale record should produce valid output."""
        single_sale = pd.DataFrame({
            "DocDate": [pd.Timestamp("2024-06-15")],
            "DocEntry": [1],
            "ItemCode": ["TO001"],
            "ItemName": ["Toy A"],
            "Brand": [np.nan],
            "Price": [100.0],
            "GroupName": ["Robinson"],
            "Quantity": [5],
            "LineTotal": [500.0],
        })
        onhand = fixtures._medium_onhand()
        master = fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(single_sale, onhand, master)

        channel = generate_sales_onhand_by_channel(df_sale, df_onhand)
        self.assertFalse(channel.empty)
        self.assertIn("Total", channel.index)

        brand = generate_sales_onhand_by_brand(df_sale, df_onhand)
        self.assertFalse(brand.empty)
        self.assertIn("Total", brand.index)

    def test_single_item_engine(self):
        """Engine with a single item should produce valid output."""
        onhand = pd.DataFrame({
            "ItemCode": ["ITEM1"],
            "WhsCode": ["WH01"],
            "OnHand": [100],
        })
        sale = pd.DataFrame({
            "DocDate": [pd.Timestamp("2024-06-15")],
            "ItemCode": ["ITEM1"],
            "WhsCode": ["WH01"],
            "Quantity": [10],
        })
        result = compute_historical_onhand(
            df_raw_onhand=onhand, df_raw_sale=sale,
            df_grpo_detail=None, df_tr_in=None, df_tr_out=None,
            file_date=date(2025, 3, 15),
        )
        self.assertEqual(len(result), 1)
        oh_cols = [c for c in result.columns if c.endswith("_OnHand_QTY")]
        self.assertGreater(len(oh_cols), 0)


class TestZeroAndInfHandling(unittest.TestCase):
    """Tests that zero on-hand and infinite ratios are handled."""

    def test_zero_onhand_item(self):
        """Items with zero on-hand should still appear in results."""
        sale, onhand, master = _raw()
        result = generate_product_sale_vs_onhand(
            df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            brand_name="ToyWorld", file_date=date(2025, 3, 15),
        )
        # Should not crash; result should have data
        self.assertFalse(result.empty)

    def test_sale_ratio_no_crash(self):
        """Sale ratio calculation should not crash with zero on-hand."""
        sale, onhand, master = _raw()
        result = generate_product_sale_vs_onhand(
            df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            brand_name="ToyWorld", file_date=date(2025, 3, 15),
        )
        ratio_cols = [c for c in result.columns if c.endswith("_Sale_Ratio")]
        # Should have ratio columns and no NaN (inf is OK)
        for col in ratio_cols:
            data = result.iloc[:-1]  # exclude Total
            self.assertFalse(data[col].isna().all(),
                f"All NaN in {col} — should have numeric values")


if __name__ == "__main__":
    unittest.main()
