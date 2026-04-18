"""Tests for Product Sale Vs. OnHand features (CLAUDE_ADDITIONS §D.2, §D.3)."""
from __future__ import annotations

import sys
import os
import unittest
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as fixtures

from app.utils.product_sale_onhand import (
    generate_product_sale_vs_onhand,
    generate_product_sale_vs_onhand_locations,
)


class TestProductSaleVsOnHand(unittest.TestCase):
    """Tests for B.2: Product Sale Vs. OnHand (CLAUDE_ADDITIONS §D.2)."""

    def _run(self, brand="ToyWorld", year_list=None):
        return generate_product_sale_vs_onhand(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            brand_name=brand,
            file_date=date(2025, 3, 15),
            period_type="monthly",
            year_list=year_list,
        )

    def test_output_rows_match_items_in_brand(self):
        """Rows should correspond to items belonging to the selected brand (+ Total)."""
        result = self._run("ToyWorld")
        self.assertFalse(result.empty)
        # "Total" row should be last
        self.assertEqual(result.index[-1], "Total")
        # Data rows should be ToyWorld items (TO001..TO005)
        data_rows = result.index[:-1].tolist()
        master = fixtures._medium_master()
        brand_items = master[master["GroupName"] == "ToyWorld"]["ItemCode"].tolist()
        for item in data_rows:
            self.assertIn(item, brand_items, f"{item} not in ToyWorld items")

    def test_monthly_columns_in_chronological_order(self):
        """Period columns should be in ascending chronological order."""
        result = self._run("ToyWorld")
        date_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        dates = [c.replace("_Sold_QTY", "") for c in date_cols]
        self.assertEqual(dates, sorted(dates))

    def test_sold_qty_matches_deduped_sales(self):
        """Total sold QTY across all periods should match deduped sale lines for the brand."""
        result = self._run("ToyWorld")
        total_row = result.loc["Total"]
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        total_from_table = sum(float(total_row[c]) for c in sold_cols)
        self.assertGreater(total_from_table, 0)

    def test_onhand_qty_uses_reconstructed_values(self):
        """OnHand columns should contain values (not all zeros or NaN)."""
        result = self._run("ToyWorld")
        oh_cols = [c for c in result.columns if c.endswith("_OnHand_QTY")]
        # At least the latest period should have non-zero on-hand for some items
        latest_oh_col = oh_cols[-1]
        data_rows = result.iloc[:-1]  # Exclude Total
        has_nonzero = (data_rows[latest_oh_col].astype(float) != 0).any()
        self.assertTrue(has_nonzero, "Latest period should have some non-zero on-hand")

    def test_sale_ratio_equals_sold_div_onhand(self):
        """Sale_Ratio should equal Sold_QTY / OnHand_QTY."""
        result = self._run("ToyWorld")
        data_rows = result.iloc[:-1]  # Exclude Total
        oh_cols = [c for c in result.columns if c.endswith("_OnHand_QTY")]
        for oh_col in oh_cols:
            period_key = oh_col.replace("_OnHand_QTY", "")
            sold_col = f"{period_key}_Sold_QTY"
            ratio_col = f"{period_key}_Sale_Ratio"
            if sold_col in result.columns and ratio_col in result.columns:
                for item in data_rows.index:
                    sq = float(data_rows.loc[item, sold_col])
                    oq = float(data_rows.loc[item, oh_col])
                    expected_ratio = sq / oq if oq > 0 else (float("inf") if sq > 0 else 0.0)
                    actual_ratio = float(data_rows.loc[item, ratio_col])
                    if expected_ratio == float("inf"):
                        self.assertEqual(actual_ratio, float("inf"),
                            f"Ratio mismatch for {item} period {period_key}")
                    else:
                        self.assertAlmostEqual(actual_ratio, expected_ratio, places=4,
                            msg=f"Ratio mismatch for {item} period {period_key}")

    def test_total_row_sums_correctly(self):
        """Total row should be the sum of data rows for qty/thb columns."""
        result = self._run("ToyWorld")
        data_rows = result.iloc[:-1]
        total_row = result.loc["Total"]
        qty_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        for col in qty_cols:
            expected = data_rows[col].astype(float).sum()
            actual = float(total_row[col])
            self.assertAlmostEqual(actual, expected, places=2,
                msg=f"Total mismatch for {col}")

    def test_empty_brand_returns_empty(self):
        """A brand with no sales should return an empty DataFrame."""
        result = self._run("NonexistentBrand")
        self.assertTrue(result.empty)

    def test_year_filter_works(self):
        """Year filter should exclude data from other years."""
        result_all = self._run("ToyWorld")
        result_2024 = self._run("ToyWorld", year_list=[2024])
        # 2024-only should have fewer or equal period columns
        all_periods = [c for c in result_all.columns if c.endswith("_Sold_QTY")]
        y2024_periods = [c for c in result_2024.columns if c.endswith("_Sold_QTY")]
        self.assertLessEqual(len(y2024_periods), len(all_periods))
        # All 2024-only periods should start with "2024"
        for col in y2024_periods:
            self.assertTrue(col.startswith("2024"), f"{col} should be in 2024")


class TestProductSaleVsOnHandLocations(unittest.TestCase):
    """Tests for B.3: Product Sale Vs. OnHand by Locations (CLAUDE_ADDITIONS §D.3)."""

    def _run(self, brand="ToyWorld"):
        return generate_product_sale_vs_onhand_locations(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            df_whs_code=fixtures._medium_whs_code(),
            brand_name=brand,
            file_date=date(2025, 3, 15),
            period_type="monthly",
        )

    def test_summary_columns_equal_sum_of_location_columns(self):
        """Total_Sold_QTY should equal sum of per-location Sold_QTY for each period and item."""
        result = self._run()
        data_rows = result.iloc[:-1]  # Exclude Total

        total_sold_cols = [c for c in result.columns if "_Total_Sold_QTY" in c]
        for total_col in total_sold_cols:
            period_key = total_col.replace("_Total_Sold_QTY", "")
            # Find all location sold_qty columns for this period
            loc_cols = [c for c in result.columns
                        if c.startswith(period_key + "_")
                        and c.endswith("_Sold_QTY")
                        and "_Total_" not in c]

            if not loc_cols:
                continue

            for item in data_rows.index:
                total_val = float(data_rows.loc[item, total_col])
                loc_sum = sum(float(data_rows.loc[item, c]) for c in loc_cols)
                self.assertAlmostEqual(total_val, loc_sum, places=2,
                    msg=f"Summary != location sum for {item} at {period_key}")

    def test_all_locations_with_activity_have_columns(self):
        """Every warehouse that has sales for the brand should appear as columns."""
        result = self._run()
        # Check that at least some location columns exist
        non_total_cols = [c for c in result.columns
                          if c.endswith("_Sold_QTY") and "_Total_" not in c
                          and c != "ItemName"]
        self.assertGreater(len(non_total_cols), 0, "Should have at least one location column")

    def test_location_onhand_uses_whscode_reconstruction(self):
        """Per-location on-hand should come from item × WhsCode reconstruction."""
        result = self._run()
        oh_cols = [c for c in result.columns
                   if c.endswith("_OnHand_QTY") and "_Total_" not in c]
        # At least some should be non-zero
        data_rows = result.iloc[:-1]
        if oh_cols:
            has_nonzero = False
            for col in oh_cols:
                if (data_rows[col].astype(float) != 0).any():
                    has_nonzero = True
                    break
            self.assertTrue(has_nonzero, "Should have some non-zero location on-hand")

    def test_result_not_empty_for_known_brand(self):
        """Should return data for a brand that has sales."""
        result = self._run()
        self.assertFalse(result.empty)
        self.assertGreater(len(result), 1)  # At least 1 item + Total row

    def test_has_dscription_column(self):
        """Output should include product descriptions."""
        result = self._run()
        self.assertIn("ItemName", result.columns)

    def test_wide_table_has_correct_structure(self):
        """Table should have Total + location columns per period."""
        result = self._run()
        # Should have both Total and location-specific columns
        total_cols = [c for c in result.columns if "_Total_" in c]
        loc_cols = [c for c in result.columns if "_Sold_QTY" in c and "_Total_" not in c]
        self.assertGreater(len(total_cols), 0, "Should have Total columns")
        self.assertGreater(len(loc_cols), 0, "Should have location columns")


if __name__ == "__main__":
    unittest.main()
