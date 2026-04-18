"""Tests for purchase cost tracking & vendor analysis."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import purchase_analytics as pua


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _sale_fixture():
    """Sales data spanning multiple months and brands."""
    dates = (
        ["2024-01-15"] * 4
        + ["2024-02-15"] * 4
        + ["2024-03-15"] * 4
    )
    return pd.DataFrame({
        "DocDate": pd.to_datetime(dates),
        "DocEntry": list(range(1, 13)),
        "ItemCode": ["A1", "A2", "B1", "B2"] * 3,
        "ItemName": ["Item A1", "Item A2", "Item B1", "Item B2"] * 3,
        "Brand": [np.nan] * 12,
        "Price": [100.0] * 12,
        "GroupName": ["Ch1", "Ch2", "Ch1", "Ch2"] * 3,
        "Quantity": [10, 5, 8, 3, 12, 6, 9, 4, 15, 7, 10, 5],
        "LineTotal": [1000, 500, 800, 300, 1200, 600, 900, 400, 1500, 700, 1000, 500],
        "WhsCode": ["WH01"] * 12,
        "Master Price": [100.0, 100.0, 100.0, 100.0] * 3,
        "Price Master": [100.0] * 12,
    })


def _onhand_fixture():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1", "B2"],
        "OnHand": [50, 30, 40, 20],
        "WhsCode": ["WH01"] * 4,
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1", "B2"],
        "GroupName": ["BrandA", "BrandA", "BrandB", "BrandB"],
        "ItemName": ["Item A1", "Item A2", "Item B1", "Item B2"],
        "Price": [100.0, 100.0, 100.0, 100.0],
    })


def _grpo_fixture():
    return pd.DataFrame({
        "DocDate": pd.to_datetime([
            "2024-01-05", "2024-01-10", "2024-02-05", "2024-02-15", "2024-03-01",
        ]),
        "ItemCode": ["A1", "B1", "A2", "B2", "A1"],
        "Quantity": [100, 80, 50, 30, 120],
        "Price": [5.0, 4.0, 6.0, 3.5, 5.5],
        "Rate": [35.0, 35.0, 36.0, 35.0, 34.0],
        "Currency": ["USD", "USD", "EUR", "USD", "USD"],
        "WhsCode": ["WH01"] * 5,
        "CardCode": ["V001", "V002", "V003", "V002", "V001"],
        "CardName": ["Vendor A", "Vendor B", "Vendor C", "Vendor B", "Vendor A"],
    })


# ---------------------------------------------------------------------------
# Test: compute_purchase_cost_trends
# ---------------------------------------------------------------------------

class TestPurchaseCostTrends(unittest.TestCase):

    def test_returns_expected_keys(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        self.assertIn("brand_trends", result)
        self.assertIn("overall_trend", result)
        self.assertIn("currency_impact", result)
        self.assertIn("summary", result)

    def test_overall_trend_periods_sorted(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        periods = [p["period"] for p in result["overall_trend"]]
        self.assertEqual(periods, sorted(periods))

    def test_brand_trends_present(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        brands = [b["brand"] for b in result["brand_trends"]]
        self.assertIn("BrandA", brands)
        self.assertIn("BrandB", brands)

    def test_currency_impact_shares_sum_100(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        if result["currency_impact"]:
            total_share = sum(c["share_pct"] for c in result["currency_impact"])
            self.assertAlmostEqual(total_share, 100.0, places=0)

    def test_summary_totals_positive(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        self.assertGreater(result["summary"]["total_purchased_thb"], 0)
        self.assertGreater(result["summary"]["unique_brands"], 0)
        self.assertGreater(result["summary"]["unique_items"], 0)

    def test_year_filter(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture(),
            year=2024,
        )
        self.assertGreater(len(result["overall_trend"]), 0)
        # Non-existent year
        result2 = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture(),
            year=2099,
        )
        self.assertEqual(len(result2["overall_trend"]), 0)

    def test_brand_filter(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture(),
            brand="BrandA",
        )
        # Only BrandA items in trends
        for bt in result["brand_trends"]:
            self.assertEqual(bt["brand"], "BrandA")

    def test_no_grpo_returns_empty(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), None
        )
        self.assertEqual(result["overall_trend"], [])
        self.assertEqual(result["summary"]["total_purchased_thb"], 0)

    def test_avg_fob_calculated(self):
        result = pua.compute_purchase_cost_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        for p in result["overall_trend"]:
            self.assertGreater(p["avg_fob_thb"], 0)


# ---------------------------------------------------------------------------
# Test: compute_purchase_vs_sold
# ---------------------------------------------------------------------------

class TestPurchaseVsSold(unittest.TestCase):

    def test_returns_expected_keys(self):
        result = pua.compute_purchase_vs_sold(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        self.assertIn("brands", result)
        self.assertIn("summary", result)

    def test_brand_rows_have_required_fields(self):
        result = pua.compute_purchase_vs_sold(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        for b in result["brands"]:
            self.assertIn("brand", b)
            self.assertIn("purchased_qty", b)
            self.assertIn("purchased_thb", b)
            self.assertIn("sold_qty", b)
            self.assertIn("sold_thb", b)
            self.assertIn("purchase_sold_ratio", b)
            self.assertIn("inventory_build_up", b)

    def test_summary_has_totals(self):
        result = pua.compute_purchase_vs_sold(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        s = result["summary"]
        self.assertGreater(s["total_purchased_thb"], 0)
        self.assertGreater(s["total_sold_thb"], 0)
        self.assertIsNotNone(s["overall_ratio"])
        self.assertEqual(s["build_up_brands"] + s["draw_down_brands"], len(result["brands"]))

    def test_purchase_sold_ratio_correct(self):
        result = pua.compute_purchase_vs_sold(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture()
        )
        for b in result["brands"]:
            if b["sold_thb"] > 0 and b["purchase_sold_ratio"] is not None:
                expected = round(b["purchased_thb"] / b["sold_thb"], 2)
                self.assertAlmostEqual(b["purchase_sold_ratio"], expected, places=1)

    def test_no_grpo_still_returns_sold(self):
        result = pua.compute_purchase_vs_sold(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), None
        )
        # Should still have brands from sales
        self.assertGreater(len(result["brands"]), 0)
        for b in result["brands"]:
            self.assertEqual(b["purchased_thb"], 0)

    def test_top_n_limit(self):
        result = pua.compute_purchase_vs_sold(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture(),
            top_n=1,
        )
        self.assertLessEqual(len(result["brands"]), 1)

    def test_year_filter(self):
        result = pua.compute_purchase_vs_sold(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _grpo_fixture(),
            year=2024,
        )
        self.assertGreater(len(result["brands"]), 0)


# ---------------------------------------------------------------------------
# Test: compute_working_capital_trends
# ---------------------------------------------------------------------------

class TestWorkingCapitalTrends(unittest.TestCase):

    def test_returns_expected_keys(self):
        result = pua.compute_working_capital_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        self.assertIn("monthly_trends", result)
        self.assertIn("summary", result)

    def test_monthly_trends_have_required_fields(self):
        result = pua.compute_working_capital_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        for m in result["monthly_trends"]:
            self.assertIn("period", m)
            self.assertIn("onhand_thb", m)
            self.assertIn("revenue_thb", m)
            self.assertIn("stock_to_sales", m)
            self.assertIn("turnover_rate", m)

    def test_summary_has_current_values(self):
        result = pua.compute_working_capital_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        s = result["summary"]
        self.assertIn("current_onhand_thb", s)
        self.assertIn("current_revenue_monthly", s)
        self.assertIn("current_turnover", s)
        self.assertIn("trend_direction", s)
        self.assertIn(s["trend_direction"], ["improving", "declining", "flat"])

    def test_onhand_thb_positive(self):
        result = pua.compute_working_capital_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        self.assertGreater(result["summary"]["current_onhand_thb"], 0)

    def test_revenue_matches_sales(self):
        result = pua.compute_working_capital_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        # Should have revenue for each month in the sales data
        self.assertGreater(len(result["monthly_trends"]), 0)
        for m in result["monthly_trends"]:
            self.assertGreater(m["revenue_thb"], 0)

    def test_window_months_limits_output(self):
        result = pua.compute_working_capital_trends(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            window_months=3,
        )
        self.assertLessEqual(len(result["monthly_trends"]), 3)

    def test_empty_sales_returns_empty(self):
        empty_sale = pd.DataFrame(columns=_sale_fixture().columns)
        result = pua.compute_working_capital_trends(
            empty_sale, _onhand_fixture(), _master_fixture()
        )
        self.assertEqual(result["monthly_trends"], [])
        self.assertEqual(result["summary"]["months_analyzed"], 0)

    def test_historical_onhand_varies_across_months(self):
        """Regression: on-hand THB must NOT be identical for every month.

        Previously compute_working_capital_trends() silently failed to call
        the historical on-hand reconstruction engine (wrong kwargs: passed
        df_item_master which is not a valid param, omitted file_date which is
        required). The except block caught the TypeError and fell back to
        current_onhand_thb for every period, producing flat/identical values.
        """
        result = pua.compute_working_capital_trends(
            _sale_fixture(),
            _onhand_fixture(),
            _master_fixture(),
            df_grpo_detail=_grpo_fixture(),
            file_date="2024-03-31",
        )
        trends = result["monthly_trends"]
        self.assertGreater(len(trends), 1, "Need at least 2 months to check variance")
        oh_values = [m["onhand_thb"] for m in trends]
        # With sales and GRPO activity across months, reconstructed on-hand
        # should differ between at least some periods.
        unique_values = set(oh_values)
        self.assertGreater(
            len(unique_values), 1,
            f"On-hand THB is identical ({oh_values[0]}) for all {len(trends)} months — "
            f"historical reconstruction likely not working. Values: {oh_values}"
        )


if __name__ == "__main__":
    unittest.main()
