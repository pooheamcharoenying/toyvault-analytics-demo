"""Tests for seasonality analysis & margin mix/waterfall computation."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import seasonality_margin as sm


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _sale_fixture():
    """Sales spanning 3 years, 2 brands, 2 channels, multiple months."""
    rows = []
    doc = 1
    for year in [2022, 2023, 2024]:
        for month in [1, 3, 6, 9, 12]:
            date_str = f"{year}-{month:02d}-15"
            for item, brand, channel, qty, total in [
                ("A1", np.nan, "Ch1", 10 + month, 1000 + month * 100),
                ("A2", np.nan, "Ch2", 5 + month, 500 + month * 50),
                ("B1", np.nan, "Ch1", 8 + month, 800 + month * 80),
                ("B2", np.nan, "Ch2", 3 + month, 300 + month * 30),
            ]:
                rows.append({
                    "DocDate": pd.Timestamp(date_str),
                    "DocEntry": doc,
                    "ItemCode": item,
                    "ItemName": f"Item {item}",
                    "Brand": brand,
                    "Price": 100.0,
                    "GroupName": channel,
                    "Quantity": qty,
                    "LineTotal": total,
                    "WhsCode": "WH01",
                    "Master Price": 100.0,
                    "Price Master": 100.0,
                })
                doc += 1
    return pd.DataFrame(rows)


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
    """GRPO data with FOB costs for margin analysis."""
    rows = []
    doc = 1
    for year in [2023, 2024]:
        for month in [1, 3, 6, 9, 12]:
            for item, qty, price, rate in [
                ("A1", 20, 5.0, 35.0),
                ("A2", 10, 8.0, 35.0),
                ("B1", 15, 3.0, 35.0),
                ("B2", 8, 10.0, 35.0),
            ]:
                rows.append({
                    "DocDate": pd.Timestamp(f"{year}-{month:02d}-01"),
                    "DocEntry": doc,
                    "ItemCode": item,
                    "Quantity": qty,
                    "Price": price,
                    "Rate": rate,
                    "Currency": "USD",
                    "WhsCode": "WH01",
                    "CardCode": "V001",
                    "CardName": "Vendor1",
                })
                doc += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Seasonality Tests
# ---------------------------------------------------------------------------

class TestSeasonalityAnalysis(unittest.TestCase):

    def setUp(self):
        self.sale = _sale_fixture()
        self.onhand = _onhand_fixture()
        self.master = _master_fixture()

    def test_basic_structure(self):
        """Result should have all required top-level keys."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        for key in ["monthly_patterns", "yearly_totals", "seasonal_index",
                     "current_vs_pattern", "yoy_growth", "summary"]:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_monthly_patterns_count(self):
        """Should have 12 monthly pattern entries."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        self.assertEqual(len(result["monthly_patterns"]), 12)

    def test_seasonal_index_averages_to_100(self):
        """Seasonal index should average approximately 100."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        indices = [s["index"] for s in result["seasonal_index"]]
        avg = sum(indices) / len(indices)
        # Only months with data contribute; months with 0 avg pull down
        # The average of indices over ALL 12 months = 100 only if all months have data
        # Our fixture has data for months 1,3,6,9,12 only, so months without data = 0 index
        # Sum of all indices / 12 would NOT be 100 in this case
        # But sum of non-zero indices / count_of_active_months * 12/12 should work
        # Actually the seasonal index formula: each month's avg / overall avg * 100
        # So average of all 12 = (sum of avgs / overall_avg) * 100 / 12
        # = total_of_monthly_avgs / (total_of_monthly_avgs/12) * 100 / 12 = 100
        # This holds because overall avg = sum(monthly_avgs)/12
        self.assertAlmostEqual(avg, 100.0, places=0)

    def test_years_analyzed(self):
        """Should detect all 3 years in the data."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        self.assertEqual(result["summary"]["years_analyzed"], 3)

    def test_current_year(self):
        """Current year should be the max year in data."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        self.assertEqual(result["summary"]["current_year"], 2024)

    def test_peak_trough_exist(self):
        """Peak and trough months should be set."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        self.assertIsNotNone(result["summary"]["peak_month"])
        self.assertIsNotNone(result["summary"]["trough_month"])

    def test_yoy_growth_count(self):
        """YoY growth should have one entry per year."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        self.assertEqual(len(result["yoy_growth"]), 3)

    def test_yoy_growth_first_year_no_pct(self):
        """First year should have no growth percentage."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        first = result["yoy_growth"][0]
        self.assertIsNone(first["growth_pct"])

    def test_brand_filter(self):
        """Filtering by brand should produce results for that brand only."""
        result = sm.compute_seasonality_analysis(
            self.sale, self.onhand, self.master,
            dimension="brand", filter_value="BrandA"
        )
        self.assertGreater(len(result["monthly_patterns"]), 0)
        self.assertEqual(result["summary"]["years_analyzed"], 3)

    def test_channel_filter(self):
        """Filtering by channel should produce results."""
        result = sm.compute_seasonality_analysis(
            self.sale, self.onhand, self.master,
            dimension="channel", filter_value="Ch1"
        )
        self.assertGreater(len(result["monthly_patterns"]), 0)

    def test_empty_data(self):
        """Empty sale data should return empty structure."""
        empty = pd.DataFrame(columns=self.sale.columns)
        result = sm.compute_seasonality_analysis(empty, self.onhand, self.master)
        self.assertEqual(result["monthly_patterns"], [])
        self.assertEqual(result["summary"]["years_analyzed"], 0)

    def test_nonexistent_brand_filter(self):
        """Filtering by nonexistent brand should return empty."""
        result = sm.compute_seasonality_analysis(
            self.sale, self.onhand, self.master,
            dimension="brand", filter_value="NoSuchBrand"
        )
        self.assertEqual(result["monthly_patterns"], [])

    def test_current_vs_pattern_structure(self):
        """Current vs pattern should have 12 entries with correct keys."""
        result = sm.compute_seasonality_analysis(self.sale, self.onhand, self.master)
        cvp = result["current_vs_pattern"]
        self.assertEqual(len(cvp), 12)
        for entry in cvp:
            self.assertIn("month", entry)
            self.assertIn("month_name", entry)
            self.assertIn("historical_avg", entry)
            self.assertIn("current_year", entry)
            self.assertIn("pct_vs_avg", entry)


# ---------------------------------------------------------------------------
# Margin Mix Tests
# ---------------------------------------------------------------------------

class TestMarginMixAnalysis(unittest.TestCase):

    def setUp(self):
        self.sale = _sale_fixture()
        self.onhand = _onhand_fixture()
        self.master = _master_fixture()
        self.grpo = _grpo_fixture()

    def test_basic_structure(self):
        """Result should have all required top-level keys."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        for key in ["margin_trend", "brand_contributions", "waterfall",
                     "margin_drivers", "summary"]:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_margin_trend_has_periods(self):
        """Margin trend should have multiple periods."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        self.assertGreater(len(result["margin_trend"]), 0)

    def test_margin_trend_values(self):
        """Each margin trend entry should have revenue, fob_cost, margin."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        for entry in result["margin_trend"]:
            self.assertIn("period", entry)
            self.assertIn("revenue", entry)
            self.assertIn("fob_cost", entry)
            self.assertIn("gross_margin", entry)
            self.assertIn("margin_pct", entry)
            # Margin = revenue - fob_cost
            expected = entry["revenue"] - entry["fob_cost"]
            self.assertAlmostEqual(entry["gross_margin"], expected, places=1)

    def test_brand_contributions_not_empty(self):
        """Should have brand contributions."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        self.assertGreater(len(result["brand_contributions"]), 0)

    def test_brand_margin_pct_calculation(self):
        """Margin % should be gross_margin / revenue * 100."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        for bc in result["brand_contributions"]:
            if bc["revenue"] > 0:
                expected_pct = bc["gross_margin"] / bc["revenue"] * 100.0
                self.assertAlmostEqual(bc["margin_pct"], round(expected_pct, 1), places=0)

    def test_waterfall_entries(self):
        """Waterfall should have entries with cumulative values."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        wf = result["waterfall"]
        self.assertGreater(len(wf), 0)
        for entry in wf:
            self.assertIn("brand", entry)
            self.assertIn("margin_contribution_thb", entry)
            self.assertIn("cumulative", entry)

    def test_margin_drivers_structure(self):
        """Margin drivers should have positive and negative lists."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        self.assertIn("positive", result["margin_drivers"])
        self.assertIn("negative", result["margin_drivers"])

    def test_summary_values(self):
        """Summary should have all required fields."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        s = result["summary"]
        self.assertIn("blended_margin_pct", s)
        self.assertIn("total_revenue", s)
        self.assertIn("total_fob_cost", s)
        self.assertIn("total_gross_margin", s)
        self.assertIn("brand_count", s)
        # total_gross_margin = total_revenue - total_fob_cost
        self.assertAlmostEqual(
            s["total_gross_margin"],
            s["total_revenue"] - s["total_fob_cost"],
            places=1
        )

    def test_year_filter(self):
        """Year filter should restrict to that year's data."""
        result_all = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo
        )
        result_2024 = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo, year=2024
        )
        # 2024-only should have fewer or equal periods
        self.assertLessEqual(
            len(result_2024["margin_trend"]),
            len(result_all["margin_trend"])
        )

    def test_no_grpo_returns_empty(self):
        """Without GRPO data, should return empty structure."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, None
        )
        self.assertEqual(result["margin_trend"], [])
        self.assertEqual(result["summary"]["blended_margin_pct"], 0)

    def test_empty_grpo_returns_empty(self):
        """Empty GRPO dataframe should return empty structure."""
        empty_grpo = pd.DataFrame(columns=self.grpo.columns)
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, empty_grpo
        )
        self.assertEqual(result["margin_trend"], [])

    def test_top_n_limits_brands(self):
        """top_n should limit the number of brands in contributions."""
        result = sm.compute_margin_mix_analysis(
            self.sale, self.onhand, self.master, self.grpo, top_n=1
        )
        self.assertLessEqual(len(result["brand_contributions"]), 1)


if __name__ == "__main__":
    unittest.main()
