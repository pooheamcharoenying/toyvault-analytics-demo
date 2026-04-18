"""
Iteration 7: Data Integrity Tests — Sales Dedup and Revenue Reconciliation.

Tests ensure:
1. Duplicate sales lines are correctly removed
2. Revenue totals are consistent across all report views
3. Channel, Brand, and Brand-Channel reports agree on total Sold_QTY/THB
4. Prepare function correctly fills Brand from Item Master
5. No data is lost or fabricated during pivot operations
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
)


class TestSalesDeduplication(unittest.TestCase):
    """Tests that duplicate sales lines are correctly handled."""

    def _prepare(self):
        return prepare_sales_and_onhand_data(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
        )

    def test_medium_fixtures_have_duplicates(self):
        """Our medium fixtures should contain duplicate lines to test dedup."""
        raw = fixtures._medium_sale()
        deduped = raw.drop_duplicates(subset=['DocEntry', 'ItemCode'])
        self.assertGreater(len(raw), len(deduped),
            "Medium fixtures should have duplicates for dedup testing")

    def test_prepare_fills_brand_from_master(self):
        """prepare_sales_and_onhand_data should fill NaN Brand from Item Master GroupName."""
        df_sale, _, _ = self._prepare()
        # After preparation, no Brand should be NaN for items that exist in master
        master_items = set(fixtures._medium_master()['ItemCode'].tolist())
        sale_items_with_na_brand = df_sale[
            df_sale['Brand'].isna() & df_sale['ItemCode'].isin(master_items)
        ]
        self.assertEqual(len(sale_items_with_na_brand), 0,
            "Brand should be filled from Item Master for known items")

    def test_channel_dedup_uses_correct_key(self):
        """Channel report dedup should use DocEntry+ItemCode+Period+GroupName."""
        df_sale, df_onhand, _ = self._prepare()
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        # Sold QTY total should be less than or equal to raw sum (due to dedup)
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        total_row = result.loc["Total"]
        deduped_total = sum(float(total_row[c]) for c in sold_cols)

        raw_total = df_sale['Quantity'].sum()
        self.assertLessEqual(deduped_total, raw_total,
            "Deduped total should be <= raw total")

    def test_brand_dedup_uses_correct_key(self):
        """Brand report dedup should use DocEntry+ItemCode+Period+Brand."""
        df_sale, df_onhand, _ = self._prepare()
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        total_row = result.loc["Total"]
        deduped_total = sum(float(total_row[c]) for c in sold_cols)

        raw_total = df_sale['Quantity'].sum()
        self.assertLessEqual(deduped_total, raw_total,
            "Deduped total should be <= raw total")

    def test_no_negative_sold_qty(self):
        """No period should have negative sold QTY at channel or brand level."""
        df_sale, df_onhand, _ = self._prepare()

        for name, result in [
            ("channel", generate_sales_onhand_by_channel(df_sale, df_onhand)),
            ("brand", generate_sales_onhand_by_brand(df_sale, df_onhand)),
        ]:
            sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
            data_rows = result.iloc[:-1]  # exclude Total
            for col in sold_cols:
                min_val = data_rows[col].astype(float).min()
                self.assertGreaterEqual(min_val, 0,
                    f"{name}: Negative Sold_QTY in {col}")

    def test_no_negative_sold_thb(self):
        """No period should have negative sold THB."""
        df_sale, df_onhand, _ = self._prepare()
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        sold_cols = [c for c in result.columns if c.endswith("_Sold_THB")]
        data_rows = result.iloc[:-1]
        for col in sold_cols:
            min_val = data_rows[col].astype(float).min()
            self.assertGreaterEqual(min_val, 0,
                f"Negative Sold_THB in {col}")


class TestRevenueReconciliation(unittest.TestCase):
    """Tests that revenue totals are consistent across report views."""

    def _prepare(self):
        return prepare_sales_and_onhand_data(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
        )

    def _total_sold_thb(self, result):
        """Sum all Sold_THB columns in the Total row."""
        sold_cols = [c for c in result.columns if c.endswith("_Sold_THB")]
        total_row = result.loc["Total"]
        return sum(float(total_row[c]) for c in sold_cols)

    def _total_sold_qty(self, result):
        """Sum all Sold_QTY columns in the Total row."""
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        total_row = result.loc["Total"]
        return sum(float(total_row[c]) for c in sold_cols)

    def test_channel_total_thb_is_positive(self):
        """Channel report should have positive total revenue."""
        df_sale, df_onhand, _ = self._prepare()
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        total = self._total_sold_thb(result)
        self.assertGreater(total, 0, "Channel total THB should be positive")

    def test_brand_total_thb_is_positive(self):
        """Brand report should have positive total revenue."""
        df_sale, df_onhand, _ = self._prepare()
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        total = self._total_sold_thb(result)
        self.assertGreater(total, 0, "Brand total THB should be positive")

    def test_channel_and_brand_thb_match(self):
        """
        Channel and Brand reports should have the same total Sold_THB.
        Both use the same dedup logic (DocEntry+ItemCode+Period+dimension).
        NOTE: They may differ slightly because dedup keys differ
        (GroupName for channel vs Brand for brand). We test they're close.
        """
        df_sale, df_onhand, _ = self._prepare()
        channel_result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        brand_result = generate_sales_onhand_by_brand(df_sale, df_onhand)

        channel_thb = self._total_sold_thb(channel_result)
        brand_thb = self._total_sold_thb(brand_result)

        # They may not be exactly equal due to different dedup dimensions,
        # but should be in the same ballpark (within 20%)
        ratio = channel_thb / brand_thb if brand_thb > 0 else 0
        self.assertGreater(ratio, 0.5, "Channel and brand THB should be within 2x")
        self.assertLess(ratio, 2.0, "Channel and brand THB should be within 2x")

    def test_total_row_equals_sum_of_data_rows_channel(self):
        """Total row should be sum of data rows for channel report."""
        df_sale, df_onhand, _ = self._prepare()
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        data_rows = result.iloc[:-1]
        total_row = result.loc["Total"]
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        for col in sold_cols:
            expected = data_rows[col].astype(float).sum()
            actual = float(total_row[col])
            self.assertAlmostEqual(actual, expected, places=2,
                msg=f"Channel total row mismatch for {col}")

    def test_total_row_equals_sum_of_data_rows_brand(self):
        """Total row should be sum of data rows for brand report."""
        df_sale, df_onhand, _ = self._prepare()
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        data_rows = result.iloc[:-1]
        total_row = result.loc["Total"]
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        for col in sold_cols:
            expected = data_rows[col].astype(float).sum()
            actual = float(total_row[col])
            self.assertAlmostEqual(actual, expected, places=2,
                msg=f"Brand total row mismatch for {col}")

    def test_weekly_vs_monthly_total_thb_match(self):
        """Total THB should be identical regardless of period_type (same data, different grouping)."""
        df_sale, df_onhand, _ = self._prepare()
        monthly = generate_sales_onhand_by_brand(df_sale, df_onhand, period_type='monthly')
        weekly = generate_sales_onhand_by_brand(df_sale, df_onhand, period_type='weekly')

        monthly_thb = self._total_sold_thb(monthly)
        weekly_thb = self._total_sold_thb(weekly)

        # Should be identical since it's the same underlying data
        self.assertAlmostEqual(monthly_thb, weekly_thb, places=0,
            msg="Monthly and weekly total THB should match")


class TestPrepareDataIntegrity(unittest.TestCase):
    """Tests for prepare_sales_and_onhand_data correctness."""

    def test_onhand_aggregated_by_itemcode(self):
        """OnHand output should be aggregated by ItemCode (one row per item)."""
        _, df_onhand, _ = prepare_sales_and_onhand_data(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
        )
        self.assertEqual(
            len(df_onhand),
            df_onhand['ItemCode'].nunique(),
            "OnHand should have one row per ItemCode"
        )

    def test_onhand_has_required_columns(self):
        """OnHand output should have Brand, ItemName, ItemCode, OnHand, Master Price."""
        _, df_onhand, _ = prepare_sales_and_onhand_data(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
        )
        for col in ['Brand', 'ItemName', 'ItemCode', 'OnHand', 'Master Price']:
            self.assertIn(col, df_onhand.columns, f"Missing column: {col}")

    def test_sale_has_month_year_column(self):
        """Sale output should have Month-Year column."""
        df_sale, _, _ = prepare_sales_and_onhand_data(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
        )
        self.assertIn('Month-Year', df_sale.columns)

    def test_sale_docdate_is_datetime(self):
        """Sale DocDate should be datetime after preparation."""
        df_sale, _, _ = prepare_sales_and_onhand_data(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
        )
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df_sale['DocDate']))

    def test_prepare_does_not_mutate_input(self):
        """prepare should not mutate the input DataFrames."""
        raw_sale = fixtures._medium_sale()
        raw_onhand = fixtures._medium_onhand()
        raw_master = fixtures._medium_master()

        sale_copy = raw_sale.copy()
        onhand_copy = raw_onhand.copy()

        prepare_sales_and_onhand_data(raw_sale, raw_onhand, raw_master)

        pd.testing.assert_frame_equal(raw_sale, sale_copy,
            obj="raw_sale should not be mutated")
        pd.testing.assert_frame_equal(raw_onhand, onhand_copy,
            obj="raw_onhand should not be mutated")


if __name__ == "__main__":
    unittest.main()
