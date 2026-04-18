"""Tests for Iteration 6: Brand matrix OnHand using full inventory engine."""
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
    generate_sales_onhand_by_brand,
)


class TestBrandMatrixWithEngine(unittest.TestCase):
    """Tests that generate_sales_onhand_by_brand uses the inventory engine when params provided."""

    def _prepare(self):
        """Run prepare_sales_and_onhand_data to get df_sale and df_onhand."""
        return prepare_sales_and_onhand_data(
            df_raw_sale=fixtures._medium_sale(),
            df_raw_onhand=fixtures._medium_onhand(),
            df_item_master=fixtures._medium_master(),
        )

    def _run_with_engine(self, period_type="monthly"):
        df_sale, df_onhand, _ = self._prepare()
        return generate_sales_onhand_by_brand(
            df_sale,
            df_onhand,
            period_type=period_type,
            df_raw_onhand=fixtures._medium_onhand(),
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            file_date=date(2025, 3, 15),
            df_item_master=fixtures._medium_master(),
        )

    def _run_without_engine(self, period_type="monthly"):
        df_sale, df_onhand, _ = self._prepare()
        return generate_sales_onhand_by_brand(
            df_sale,
            df_onhand,
            period_type=period_type,
        )

    def test_engine_result_not_empty(self):
        """Engine path should produce non-empty results."""
        result = self._run_with_engine()
        self.assertFalse(result.empty)

    def test_has_onhand_columns(self):
        """Result should have OnHand_QTY columns for each period."""
        result = self._run_with_engine()
        oh_cols = [c for c in result.columns if c.endswith("_OnHand_QTY")]
        self.assertGreater(len(oh_cols), 0)

    def test_has_sold_columns(self):
        """Result should have Sold_QTY and Sold_THB columns."""
        result = self._run_with_engine()
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        self.assertGreater(len(sold_cols), 0)

    def test_has_total_row(self):
        """Result should have a Total row."""
        result = self._run_with_engine()
        self.assertIn("Total", result.index)

    def test_total_row_sums_correctly(self):
        """Total row should be sum of data rows for sold columns."""
        result = self._run_with_engine()
        data_rows = result.iloc[:-1]
        total_row = result.loc["Total"]
        sold_cols = [c for c in result.columns if c.endswith("_Sold_QTY")]
        for col in sold_cols:
            expected = data_rows[col].astype(float).sum()
            actual = float(total_row[col])
            self.assertAlmostEqual(actual, expected, places=2,
                msg=f"Total mismatch for {col}")

    def test_engine_vs_fallback_sold_qty_match(self):
        """Sold QTY should be identical whether engine or fallback is used."""
        engine_result = self._run_with_engine()
        fallback_result = self._run_without_engine()

        sold_cols_e = sorted([c for c in engine_result.columns if c.endswith("_Sold_QTY")])
        sold_cols_f = sorted([c for c in fallback_result.columns if c.endswith("_Sold_QTY")])
        # Sold columns should be the same
        self.assertEqual(sold_cols_e, sold_cols_f)

        # Sold QTY values should match (engine doesn't change sales)
        for col in sold_cols_e:
            for brand in engine_result.index:
                if brand in fallback_result.index:
                    self.assertAlmostEqual(
                        float(engine_result.at[brand, col]),
                        float(fallback_result.at[brand, col]),
                        places=2,
                        msg=f"Sold QTY mismatch for {brand}/{col}"
                    )

    def test_engine_onhand_differs_from_fallback(self):
        """
        With GRPO/TR movements, engine OnHand should differ from simple fallback
        for at least some periods (unless movements are exactly zero, which is
        unlikely with our medium fixtures).
        """
        engine_result = self._run_with_engine()
        fallback_result = self._run_without_engine()

        oh_cols = [c for c in engine_result.columns if c.endswith("_OnHand_QTY")]
        # Check that at least one value differs (engine accounts for GRPO/TR)
        found_diff = False
        for col in oh_cols:
            if col not in fallback_result.columns:
                continue
            for brand in engine_result.index:
                if brand == "Total":
                    continue
                if brand not in fallback_result.index:
                    continue
                e_val = float(engine_result.at[brand, col])
                f_val = float(fallback_result.at[brand, col])
                if not np.isclose(e_val, f_val, atol=0.01):
                    found_diff = True
                    break
            if found_diff:
                break
        self.assertTrue(found_diff,
            "Engine and fallback should produce different OnHand values when GRPO/TR data exists")

    def test_onhand_thb_is_positive_or_zero(self):
        """OnHand THB values should be >= 0 for most brands."""
        result = self._run_with_engine()
        thb_cols = [c for c in result.columns if c.endswith("_OnHand_THB")]
        # Check latest period Total row
        if thb_cols:
            latest_thb = float(result.loc["Total", thb_cols[-1]])
            self.assertGreaterEqual(latest_thb, 0)

    def test_column_ordering(self):
        """Columns should be in date order with metrics grouped per date."""
        result = self._run_with_engine()
        cols = list(result.columns)
        # Extract dates
        dates = []
        for c in cols:
            parts = c.split("_", 1)
            if len(parts) == 2:
                dates.append(parts[0])
        unique_dates = list(dict.fromkeys(dates))  # preserve order, remove dups
        self.assertEqual(unique_dates, sorted(unique_dates),
            "Dates should be in ascending order")


if __name__ == "__main__":
    unittest.main()
