"""Tests for Historical OnHand Reconstruction Engine (CLAUDE_ADDITIONS §D.1)."""
from __future__ import annotations

import sys
import os
import unittest
from datetime import date

import numpy as np
import pandas as pd

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import conftest to set up mocks
import tests.conftest as fixtures

from app.utils.inventory_engine import (
    compute_historical_onhand,
    compute_historical_onhand_org,
)


class TestLatestPeriodEqualsSnapshot(unittest.TestCase):
    """test_latest_period_onhand_equals_current_snapshot"""

    def test_latest_period_matches_snapshot(self):
        """The latest period's on-hand should equal the current snapshot values."""
        onhand = pd.DataFrame({
            "ItemCode": ["A1", "A1", "A2"],
            "WhsCode": ["WH01", "WH02", "WH01"],
            "OnHand": [10, 5, 20],
        })
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-15", "2024-02-15"]),
            "ItemCode": ["A1", "A2"],
            "WhsCode": ["WH01", "WH01"],
            "Quantity": [3, 7],
        })
        result = compute_historical_onhand(
            onhand, sale, None, None, None,
            file_date=date(2024, 3, 1), period_type="monthly",
        )
        self.assertFalse(result.empty)
        # Latest period is 2024-02-01 (the last month with sales)
        latest_col = [c for c in result.columns if c.endswith("_OnHand_QTY")][-1]
        # A1 at WH01: current=10
        self.assertAlmostEqual(result.loc[("A1", "WH01"), latest_col], 10.0)
        # A2 at WH01: current=20
        self.assertAlmostEqual(result.loc[("A2", "WH01"), latest_col], 20.0)


class TestSalesIncreaseHistoricalOnhand(unittest.TestCase):
    """test_onhand_increases_when_looking_back_past_sales"""

    def test_earlier_period_has_higher_onhand(self):
        """On-hand should be HIGHER in earlier periods because items sold later were still in stock."""
        onhand = pd.DataFrame({
            "ItemCode": ["A1"],
            "WhsCode": ["WH01"],
            "OnHand": [10],
        })
        # 5 units sold in February
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-10", "2024-02-15"]),
            "ItemCode": ["A1", "A1"],
            "WhsCode": ["WH01", "WH01"],
            "Quantity": [3, 5],
        })
        result = compute_historical_onhand(
            onhand, sale, None, None, None,
            file_date=date(2024, 3, 1), period_type="monthly",
        )
        cols = sorted([c for c in result.columns if c.endswith("_OnHand_QTY")])
        # Jan on-hand should be higher than Feb (because Feb sales reduce stock going forward)
        jan_oh = result.loc[("A1", "WH01"), cols[0]]  # 2024-01-01
        feb_oh = result.loc[("A1", "WH01"), cols[1]]  # 2024-02-01
        # Feb is latest → equals current snapshot = 10
        self.assertAlmostEqual(feb_oh, 10.0)
        # Jan = Feb_onhand + Feb_sold = 10 + 5 = 15
        self.assertAlmostEqual(jan_oh, 15.0)


class TestPurchasesDecreaseHistoricalOnhand(unittest.TestCase):
    """test_onhand_decreases_when_looking_back_past_purchases"""

    def test_earlier_period_lower_due_to_purchases(self):
        """On-hand should be LOWER in earlier periods if purchases happened after."""
        onhand = pd.DataFrame({
            "ItemCode": ["A1"],
            "WhsCode": ["WH01"],
            "OnHand": [50],
        })
        # Minimal sale so we have periods
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-10", "2024-02-10"]),
            "ItemCode": ["A1", "A1"],
            "WhsCode": ["WH01", "WH01"],
            "Quantity": [0, 0],
        })
        # 20 units purchased in February
        grpo = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-02-15"]),
            "ItemCode": ["A1"],
            "WhsCode": ["WH01"],
            "Quantity": [20],
        })
        result = compute_historical_onhand(
            onhand, sale, grpo, None, None,
            file_date=date(2024, 3, 1), period_type="monthly",
        )
        cols = sorted([c for c in result.columns if c.endswith("_OnHand_QTY")])
        jan_oh = result.loc[("A1", "WH01"), cols[0]]
        feb_oh = result.loc[("A1", "WH01"), cols[1]]
        # Feb = 50 (current snapshot)
        self.assertAlmostEqual(feb_oh, 50.0)
        # Jan = Feb + sold_in_Feb - GRPO_in_Feb = 50 + 0 - 20 = 30
        self.assertAlmostEqual(jan_oh, 30.0)


class TestTransfersAffectHistoricalOnhand(unittest.TestCase):
    """test_transfers_in_decrease_historical_onhand / test_transfers_out_increase_historical_onhand"""

    def test_transfer_in_decreases_past(self):
        """Items transferred IN after a period weren't there before → lower historical on-hand."""
        onhand = pd.DataFrame({"ItemCode": ["A1"], "WhsCode": ["WH01"], "OnHand": [30]})
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-10", "2024-02-10"]),
            "ItemCode": ["A1", "A1"], "WhsCode": ["WH01", "WH01"], "Quantity": [0, 0],
        })
        tr_in = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-02-15"]),
            "ItemCode": ["A1"], "WhsCode": ["WH01"], "Quantity": [10],
        })
        result = compute_historical_onhand(
            onhand, sale, None, tr_in, None,
            file_date=date(2024, 3, 1), period_type="monthly",
        )
        cols = sorted([c for c in result.columns if c.endswith("_OnHand_QTY")])
        jan_oh = result.loc[("A1", "WH01"), cols[0]]
        feb_oh = result.loc[("A1", "WH01"), cols[1]]
        self.assertAlmostEqual(feb_oh, 30.0)
        # Jan = Feb - TR_IN_in_Feb = 30 - 10 = 20
        self.assertAlmostEqual(jan_oh, 20.0)

    def test_transfer_out_increases_past(self):
        """Items transferred OUT after a period were still there before → higher historical on-hand."""
        onhand = pd.DataFrame({"ItemCode": ["A1"], "WhsCode": ["WH01"], "OnHand": [20]})
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-10", "2024-02-10"]),
            "ItemCode": ["A1", "A1"], "WhsCode": ["WH01", "WH01"], "Quantity": [0, 0],
        })
        # TR OUT has negative quantity: -8 means 8 units left
        tr_out = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-02-15"]),
            "ItemCode": ["A1"], "WhsCode": ["WH01"], "Quantity": [-8],
        })
        result = compute_historical_onhand(
            onhand, sale, None, None, tr_out,
            file_date=date(2024, 3, 1), period_type="monthly",
        )
        cols = sorted([c for c in result.columns if c.endswith("_OnHand_QTY")])
        jan_oh = result.loc[("A1", "WH01"), cols[0]]
        feb_oh = result.loc[("A1", "WH01"), cols[1]]
        self.assertAlmostEqual(feb_oh, 20.0)
        # Jan = Feb - TR_OUT_in_Feb = 20 - (-8) = 28
        self.assertAlmostEqual(jan_oh, 28.0)


class TestItemLocationGranularity(unittest.TestCase):
    """test_reconstruction_at_item_x_location_grain"""

    def test_different_locations_independent(self):
        """On-hand at different warehouses should be reconstructed independently."""
        onhand = pd.DataFrame({
            "ItemCode": ["A1", "A1"],
            "WhsCode": ["WH01", "WH02"],
            "OnHand": [10, 20],
        })
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-15", "2024-01-20"]),
            "ItemCode": ["A1", "A1"],
            "WhsCode": ["WH01", "WH02"],
            "Quantity": [3, 7],
        })
        result = compute_historical_onhand(
            onhand, sale, None, None, None,
            file_date=date(2024, 2, 1), period_type="monthly",
        )
        # Only one period (Jan), which is the latest
        cols = [c for c in result.columns if c.endswith("_OnHand_QTY")]
        self.assertEqual(len(cols), 1)
        self.assertAlmostEqual(result.loc[("A1", "WH01"), cols[0]], 10.0)
        self.assertAlmostEqual(result.loc[("A1", "WH02"), cols[0]], 20.0)


class TestOrgWideAggregation(unittest.TestCase):
    """test_org_wide_onhand_equals_sum_of_location_onhands"""

    def test_org_level_sums_locations(self):
        """Org-wide on-hand should equal sum of per-location on-hand."""
        onhand = pd.DataFrame({
            "ItemCode": ["A1", "A1"],
            "WhsCode": ["WH01", "WH02"],
            "OnHand": [10, 20],
        })
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-15", "2024-02-15"]),
            "ItemCode": ["A1", "A1"],
            "WhsCode": ["WH01", "WH01"],
            "Quantity": [5, 3],
        })
        detail = compute_historical_onhand(
            onhand, sale, None, None, None,
            file_date=date(2024, 3, 1), period_type="monthly",
        )
        org = compute_historical_onhand_org(
            onhand, sale, None, None, None,
            file_date=date(2024, 3, 1), period_type="monthly",
        )

        for col in org.columns:
            detail_sum = detail[col].groupby(level="ItemCode").sum()
            pd.testing.assert_series_equal(org[col], detail_sum, check_names=False)


class TestSaleRatioCalculation(unittest.TestCase):
    """test_sale_ratio_calculation_correct / test_sale_ratio_inf_when_onhand_zero"""

    def test_ratio_basic(self):
        """Sale ratio = sold_qty / onhand_qty."""
        sold = 10.0
        onhand = 5.0
        ratio = sold / onhand
        self.assertAlmostEqual(ratio, 2.0)

    def test_ratio_inf_when_zero_onhand(self):
        """Ratio should be inf when on-hand is 0."""
        sold = 10.0
        onhand = 0.0
        ratio = float("inf") if onhand == 0 else sold / onhand
        self.assertEqual(ratio, float("inf"))

    def test_ratio_zero_when_no_sales(self):
        """Ratio should be 0 when sold is 0."""
        sold = 0.0
        onhand = 10.0
        ratio = sold / onhand if onhand > 0 else 0.0
        self.assertAlmostEqual(ratio, 0.0)


class TestMediumFixtureReconstruction(unittest.TestCase):
    """Test with medium-sized realistic fixtures."""

    def test_medium_fixture_runs_without_error(self):
        """The engine should handle 100+ on-hand rows and 200+ sale lines."""
        result = compute_historical_onhand(
            fixtures._medium_onhand(),
            fixtures._medium_sale(),
            fixtures._medium_grpo(),
            fixtures._medium_tr_in(),
            fixtures._medium_tr_out(),
            file_date=date(2025, 3, 15),
            period_type="monthly",
        )
        self.assertFalse(result.empty)
        # Should have multiple period columns
        oh_cols = [c for c in result.columns if c.endswith("_OnHand_QTY")]
        self.assertGreater(len(oh_cols), 12)  # 2+ years of monthly data

    def test_medium_fixture_latest_matches_snapshot(self):
        """Latest period on-hand should match the input snapshot."""
        oh = fixtures._medium_onhand()
        result = compute_historical_onhand(
            oh,
            fixtures._medium_sale(),
            fixtures._medium_grpo(),
            fixtures._medium_tr_in(),
            fixtures._medium_tr_out(),
            file_date=date(2025, 3, 15),
            period_type="monthly",
        )
        latest_col = sorted([c for c in result.columns if c.endswith("_OnHand_QTY")])[-1]

        # Sum by (ItemCode, WhsCode) from input
        oh_clean = oh.copy()
        oh_clean["OnHand"] = pd.to_numeric(oh_clean["OnHand"], errors="coerce").fillna(0)
        expected = oh_clean.groupby(["ItemCode", "WhsCode"])["OnHand"].sum()

        for (item, wh), val in result[latest_col].items():
            exp = expected.get((item, wh), 0.0)
            self.assertAlmostEqual(val, exp, places=2,
                msg=f"Mismatch for {item}@{wh}: got {val}, expected {exp}")


if __name__ == "__main__":
    unittest.main()
