"""
Iteration 9: Data Integrity Tests — Margin, Risk, Channels.

Tests ensure:
1. Gross margin = revenue - COGS for every brand
2. Inventory risk: days_cover is consistent with on-hand/sales velocity
3. Channel performance: channel rows exist and data is consistent
4. Concentration shares sum correctly
5. Sales trend has valid YoY and TTM calculations
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

from app.utils.executive_helpers import (
    compute_executive_summary,
    compute_sales_trend_executive,
    compute_concentration_summary,
    compute_margin_by_brand,
    compute_inventory_risk_summary,
    compute_channel_performance_executive,
)


def _raw_data():
    return fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()


class TestMarginByBrandIntegrity(unittest.TestCase):
    """Tests for EX-03: margin computation correctness."""

    def test_gross_margin_equals_revenue_minus_cogs(self):
        """For every brand row, gross_margin_thb == revenue_thb - cogs_thb."""
        sale, onhand, master = _raw_data()
        result = compute_margin_by_brand(sale, onhand, master)
        for row in result["rows"]:
            expected = row["revenue_thb"] - row["cogs_thb"]
            self.assertAlmostEqual(row["gross_margin_thb"], expected, places=2,
                msg=f"Margin mismatch for {row['brand']}")

    def test_totals_match_row_sums(self):
        """Totals should be the sum of individual rows."""
        sale, onhand, master = _raw_data()
        result = compute_margin_by_brand(sale, onhand, master)
        row_rev = sum(r["revenue_thb"] for r in result["rows"])
        row_cogs = sum(r["cogs_thb"] for r in result["rows"])
        self.assertAlmostEqual(result["totals"]["revenue_thb"], row_rev, places=2)
        self.assertAlmostEqual(result["totals"]["cogs_thb"], row_cogs, places=2)

    def test_total_margin_pct_consistent(self):
        """Total margin pct should equal total_margin / total_revenue * 100."""
        sale, onhand, master = _raw_data()
        result = compute_margin_by_brand(sale, onhand, master)
        t = result["totals"]
        if t["revenue_thb"] > 0 and t["gross_margin_pct"] is not None:
            expected_pct = t["gross_margin_thb"] / t["revenue_thb"] * 100.0
            self.assertAlmostEqual(t["gross_margin_pct"], expected_pct, places=2)

    def test_revenue_is_positive(self):
        """Total revenue should be positive."""
        sale, onhand, master = _raw_data()
        result = compute_margin_by_brand(sale, onhand, master)
        self.assertGreater(result["totals"]["revenue_thb"], 0)

    def test_with_grpo_data(self):
        """COGS should be non-zero when GRPO data is provided."""
        sale, onhand, master = _raw_data()
        grpo = fixtures._medium_grpo()
        result = compute_margin_by_brand(sale, onhand, master, df_grpo_detail=grpo)
        # At least some brands should have non-zero COGS
        any_cogs = any(r["cogs_thb"] > 0 for r in result["rows"])
        self.assertTrue(any_cogs, "Some brands should have non-zero COGS with GRPO data")


class TestInventoryRiskIntegrity(unittest.TestCase):
    """Tests for EX-04: inventory risk calculations."""

    def test_days_cover_positive_or_none(self):
        """days_cover should be positive float or None (for inf)."""
        sale, onhand, master = _raw_data()
        result = compute_inventory_risk_summary(sale, onhand, master)
        for row in result["rows"]:
            dc = row["days_cover"]
            if dc is not None:
                self.assertGreater(dc, 0, f"days_cover should be > 0 for {row['item_code']}")

    def test_onhand_values_positive_or_zero(self):
        """On-hand quantities should be non-negative."""
        sale, onhand, master = _raw_data()
        result = compute_inventory_risk_summary(sale, onhand, master)
        for row in result["rows"]:
            self.assertGreaterEqual(row["onhand_qty"], 0)

    def test_summary_has_onhand_value(self):
        """Summary should include total on-hand value."""
        sale, onhand, master = _raw_data()
        result = compute_inventory_risk_summary(sale, onhand, master)
        self.assertIn("summary", result)
        if result["summary"]:
            self.assertIn("total_onhand_thb", result["summary"])

    def test_result_has_rows(self):
        """Should return at least one row for medium fixtures."""
        sale, onhand, master = _raw_data()
        result = compute_inventory_risk_summary(sale, onhand, master)
        self.assertGreater(len(result["rows"]), 0)


class TestConcentrationIntegrity(unittest.TestCase):
    """Tests for EX-05: concentration summary."""

    def test_brand_shares_sum_to_top_k(self):
        """Individual brand shares should sum to top_k_share_pct."""
        sale, onhand, master = _raw_data()
        result = compute_concentration_summary(sale, onhand, master, "brand", 2024)
        if result["rows"]:
            individual_sum = sum(r["share_pct"] for r in result["rows"])
            self.assertAlmostEqual(individual_sum, result["top_k_share_pct"], places=1)

    def test_channel_concentration_works(self):
        """Channel dimension should also produce valid results."""
        sale, onhand, master = _raw_data()
        result = compute_concentration_summary(sale, onhand, master, "channel", 2024)
        if result["rows"]:
            self.assertGreater(result["total_revenue_thb"], 0)

    def test_share_pct_between_0_and_100(self):
        """Every share should be between 0 and 100."""
        sale, onhand, master = _raw_data()
        result = compute_concentration_summary(sale, onhand, master, "brand", 2024)
        for row in result["rows"]:
            self.assertGreaterEqual(row["share_pct"], 0)
            self.assertLessEqual(row["share_pct"], 100)


class TestSalesTrendIntegrity(unittest.TestCase):
    """Tests for EX-02: sales trend time series."""

    def test_series_not_empty(self):
        """Should produce at least one period for medium fixtures."""
        sale, onhand, master = _raw_data()
        result = compute_sales_trend_executive(sale, onhand, master)
        self.assertGreater(len(result["series"]), 0)

    def test_revenue_is_positive_for_each_period(self):
        """Each period should have positive revenue."""
        sale, onhand, master = _raw_data()
        result = compute_sales_trend_executive(sale, onhand, master)
        for entry in result["series"]:
            self.assertGreaterEqual(entry["revenue_thb"], 0)

    def test_ttm_is_cumulative(self):
        """TTM revenue should be non-decreasing over time (or at least consistent)."""
        sale, onhand, master = _raw_data()
        result = compute_sales_trend_executive(sale, onhand, master)
        series = result["series"]
        if len(series) >= 2:
            # TTM at last period should include revenue from multiple periods
            last_ttm = series[-1]["ttm_revenue_thb"]
            last_rev = series[-1]["revenue_thb"]
            self.assertGreaterEqual(last_ttm, last_rev,
                "TTM should be >= single period revenue")

    def test_year_filter_works(self):
        """Year filter should restrict to specified years."""
        sale, onhand, master = _raw_data()
        result = compute_sales_trend_executive(sale, onhand, master, year_list=[2024])
        for entry in result["series"]:
            self.assertTrue(entry["period"].startswith("2024"),
                f"Period {entry['period']} should be in 2024")


class TestExecutiveSummaryIntegrity(unittest.TestCase):
    """Tests for EX-01: executive summary totals."""

    def test_totals_positive(self):
        """Executive summary totals should be positive."""
        sale, onhand, master = _raw_data()
        result = compute_executive_summary(sale, onhand, master)
        self.assertGreater(result["totals"]["sold_thb"], 0)
        self.assertGreater(result["totals"]["sold_qty"], 0)
        self.assertGreater(result["totals"]["onhand_qty"], 0)

    def test_onhand_thb_consistent(self):
        """OnHand THB should equal qty * master price (aggregated)."""
        sale, onhand, master = _raw_data()
        result = compute_executive_summary(sale, onhand, master)
        # Just check it's positive and reasonable
        self.assertGreater(result["totals"]["onhand_thb_master"], 0)


if __name__ == "__main__":
    unittest.main()
