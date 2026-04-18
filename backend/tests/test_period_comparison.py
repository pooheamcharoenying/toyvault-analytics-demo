"""Tests for period comparison computation (OBJ-10)."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import period_comparison as pc


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _sale_fixture():
    """Sales spanning 2023-2025, multiple brands and channels."""
    rows = []
    doc = 1
    for year in [2023, 2024, 2025]:
        for month in [1, 3, 6, 9, 12]:
            date_str = f"{year}-{month:02d}-15"
            for item, channel, qty, total in [
                ("A1", "Ch1", 10 * (year - 2022), 1000 * (year - 2022)),
                ("A2", "Ch2", 5 * (year - 2022), 500 * (year - 2022)),
                ("B1", "Ch1", 8 * (year - 2022), 800 * (year - 2022)),
            ]:
                rows.append({
                    "DocDate": pd.Timestamp(date_str),
                    "DocEntry": doc,
                    "ItemCode": item,
                    "ItemName": f"Item {item}",
                    "Brand": np.nan,
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
        "ItemCode": ["A1", "A2", "B1"],
        "OnHand": [50, 30, 40],
        "WhsCode": ["WH01"] * 3,
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1"],
        "GroupName": ["BrandA", "BrandA", "BrandB"],
        "ItemName": ["Item A1", "Item A2", "Item B1"],
        "Price": [100.0, 100.0, 100.0],
    })


def _grpo_fixture():
    rows = []
    doc = 1
    for year in [2023, 2024, 2025]:
        for month in [1, 6]:
            for item, qty, price, rate in [
                ("A1", 20, 5.0, 35.0),
                ("A2", 10, 8.0, 35.0),
                ("B1", 15, 3.0, 35.0),
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
                    "CardName": "Vendor",
                })
                doc += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPeriodComparison(unittest.TestCase):
    """Test compute_period_comparison()."""

    def setUp(self):
        self.sale = _sale_fixture()
        self.onhand = _onhand_fixture()
        self.master = _master_fixture()
        self.grpo = _grpo_fixture()

    def test_full_year_comparison(self):
        """Comparing 2024 vs 2023 should return both period KPIs and changes."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_b_year=2023,
        )
        self.assertEqual(result["period_a_label"], "2024")
        self.assertEqual(result["period_b_label"], "2023")

        pa = result["period_a"]
        pb = result["period_b"]
        self.assertGreater(pa["revenue_thb"], 0)
        self.assertGreater(pb["revenue_thb"], 0)
        # 2024 has higher multiplier (year-2022=2) vs 2023 (year-2022=1)
        self.assertGreater(pa["revenue_thb"], pb["revenue_thb"])

        changes = result["changes"]
        self.assertEqual(changes["revenue_thb"]["direction"], "up")
        self.assertGreater(changes["revenue_thb"]["absolute"], 0)

    def test_quarter_comparison(self):
        """Quarter comparison should filter to the correct months."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_a_quarter=1,
            period_b_year=2023, period_b_quarter=1,
        )
        self.assertEqual(result["period_a_label"], "2024 Q1")
        self.assertEqual(result["period_b_label"], "2023 Q1")
        # Q1 has month 1 and 3 data
        pa = result["period_a"]
        self.assertGreater(pa["revenue_thb"], 0)

    def test_month_comparison(self):
        """Monthly comparison should only include that specific month."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_a_month=6,
            period_b_year=2023, period_b_month=6,
        )
        self.assertEqual(result["period_a_label"], "2024-06")
        self.assertEqual(result["period_b_label"], "2023-06")
        pa = result["period_a"]
        self.assertGreater(pa["revenue_thb"], 0)
        # Should only have 1 month in monthly breakdown
        self.assertEqual(len(pa["monthly"]), 1)
        self.assertEqual(pa["monthly"][0]["period"], "2024-06")

    def test_brand_comparison(self):
        """Brand comparison should list all brands with changes."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_b_year=2023,
        )
        brands = result["brand_comparison"]
        self.assertGreater(len(brands), 0)
        brand_names = [b["brand"] for b in brands]
        self.assertIn("BrandA", brand_names)
        self.assertIn("BrandB", brand_names)
        for b in brands:
            self.assertIn("period_a_revenue", b)
            self.assertIn("period_b_revenue", b)
            self.assertIn("revenue_change", b)

    def test_channel_comparison(self):
        """Channel comparison should list all channels with changes."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_b_year=2023,
        )
        channels = result["channel_comparison"]
        self.assertGreater(len(channels), 0)
        ch_names = [c["channel"] for c in channels]
        self.assertIn("Ch1", ch_names)
        self.assertIn("Ch2", ch_names)

    def test_changes_have_correct_structure(self):
        """Changes dict should have absolute, pct, and direction."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_b_year=2023,
        )
        changes = result["changes"]
        for key in ["revenue_thb", "sold_qty", "purchased_thb", "gross_margin_thb",
                     "transaction_count", "unique_items_sold"]:
            self.assertIn(key, changes)
            self.assertIn("absolute", changes[key])
            self.assertIn("pct", changes[key])
            self.assertIn("direction", changes[key])
            self.assertIn(changes[key]["direction"], ("up", "down", "flat"))

    def test_grpo_purchased_thb(self):
        """Purchased THB should reflect GRPO data in the period."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_b_year=2023,
        )
        pa = result["period_a"]
        # We have GRPO data for 2024 months 1 and 6
        self.assertGreater(pa["purchased_thb"], 0)

    def test_no_grpo_returns_zero_purchases(self):
        """Without GRPO data, purchased_thb should be 0."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, None,
            period_a_year=2024, period_b_year=2023,
        )
        pa = result["period_a"]
        self.assertEqual(pa["purchased_thb"], 0.0)

    def test_empty_period_returns_zeros(self):
        """A period with no data should return zero KPIs."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2020, period_b_year=2019,
        )
        self.assertEqual(result["period_a"]["revenue_thb"], 0.0)
        self.assertEqual(result["period_b"]["revenue_thb"], 0.0)

    def test_gross_margin_calculation(self):
        """Gross margin should be revenue minus purchased THB."""
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            period_a_year=2024, period_b_year=2023,
        )
        pa = result["period_a"]
        expected_margin = pa["revenue_thb"] - pa["purchased_thb"]
        self.assertAlmostEqual(pa["gross_margin_thb"], expected_margin, places=2)

    def test_period_labels(self):
        """Various granularity settings produce correct labels."""
        r1 = pc.compute_period_comparison(
            self.sale, self.onhand, self.master,
            period_a_year=2024, period_b_year=2023,
        )
        self.assertEqual(r1["period_a_label"], "2024")

        r2 = pc.compute_period_comparison(
            self.sale, self.onhand, self.master,
            period_a_year=2024, period_a_quarter=2,
            period_b_year=2023, period_b_quarter=2,
        )
        self.assertEqual(r2["period_a_label"], "2024 Q2")

        r3 = pc.compute_period_comparison(
            self.sale, self.onhand, self.master,
            period_a_year=2024, period_a_month=3,
            period_b_year=2023, period_b_month=3,
        )
        self.assertEqual(r3["period_a_label"], "2024-03")


class TestSafeChange(unittest.TestCase):
    """Test _safe_change helper."""

    def test_positive_change(self):
        result = pc._safe_change(150, 100)
        self.assertEqual(result["absolute"], 50)
        self.assertEqual(result["pct"], 50.0)
        self.assertEqual(result["direction"], "up")

    def test_negative_change(self):
        result = pc._safe_change(80, 100)
        self.assertEqual(result["absolute"], -20)
        self.assertEqual(result["pct"], -20.0)
        self.assertEqual(result["direction"], "down")

    def test_zero_previous(self):
        result = pc._safe_change(100, 0)
        self.assertEqual(result["absolute"], 100)
        self.assertIsNone(result["pct"])
        self.assertEqual(result["direction"], "up")

    def test_no_change(self):
        result = pc._safe_change(100, 100)
        self.assertEqual(result["absolute"], 0)
        self.assertEqual(result["direction"], "flat")


class TestPeriodRange(unittest.TestCase):
    """Test _period_range helper."""

    def test_full_year(self):
        start, end = pc._period_range(2024)
        self.assertEqual(start, pd.Timestamp("2024-01-01"))
        self.assertEqual(end, pd.Timestamp("2024-12-31"))

    def test_quarter(self):
        start, end = pc._period_range(2024, quarter=2)
        self.assertEqual(start, pd.Timestamp("2024-04-01"))
        self.assertEqual(end, pd.Timestamp("2024-06-30"))

    def test_month(self):
        start, end = pc._period_range(2024, month=2)
        self.assertEqual(start, pd.Timestamp("2024-02-01"))
        self.assertEqual(end, pd.Timestamp("2024-02-29"))  # 2024 is a leap year

    def test_q1(self):
        start, end = pc._period_range(2024, quarter=1)
        self.assertEqual(start, pd.Timestamp("2024-01-01"))
        self.assertEqual(end, pd.Timestamp("2024-03-31"))

    def test_q4(self):
        start, end = pc._period_range(2024, quarter=4)
        self.assertEqual(start, pd.Timestamp("2024-10-01"))
        self.assertEqual(end, pd.Timestamp("2024-12-31"))


class TestMultiPeriodComparison(unittest.TestCase):
    """Test compute_multi_period_comparison()."""

    def setUp(self):
        self.sale = _sale_fixture()
        self.onhand = _onhand_fixture()
        self.master = _master_fixture()
        self.grpo = _grpo_fixture()

    def test_two_periods(self):
        """Two-period multi comparison should work like the original."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[{"year": 2024}, {"year": 2023}],
        )
        self.assertEqual(result["period_count"], 2)
        self.assertEqual(result["labels"], ["2024", "2023"])
        self.assertEqual(len(result["periods"]), 2)
        self.assertGreater(result["periods"][0]["revenue_thb"], 0)
        self.assertGreater(result["periods"][1]["revenue_thb"], 0)
        # 2024 > 2023 because multiplier is year-2022
        self.assertGreater(result["periods"][0]["revenue_thb"], result["periods"][1]["revenue_thb"])
        self.assertEqual(result["changes"]["revenue_thb"]["direction"], "up")

    def test_three_periods(self):
        """Three-period comparison should return 3 period KPIs."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[{"year": 2025}, {"year": 2024}, {"year": 2023}],
        )
        self.assertEqual(result["period_count"], 3)
        self.assertEqual(len(result["labels"]), 3)
        self.assertEqual(len(result["periods"]), 3)
        # Revenue should be strictly descending: 2025 > 2024 > 2023
        revs = [p["revenue_thb"] for p in result["periods"]]
        self.assertGreater(revs[0], revs[1])
        self.assertGreater(revs[1], revs[2])

    def test_four_periods(self):
        """Four-period comparison should work."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[
                {"year": 2025}, {"year": 2024}, {"year": 2023},
                {"year": 2020},  # no data, should return zeros
            ],
        )
        self.assertEqual(result["period_count"], 4)
        self.assertEqual(len(result["periods"]), 4)
        # Last period (2020) has no data
        self.assertEqual(result["periods"][3]["revenue_thb"], 0.0)

    def test_quarterly_multi(self):
        """Quarterly periods should produce correct labels."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[
                {"year": 2025, "quarter": 1},
                {"year": 2024, "quarter": 1},
                {"year": 2023, "quarter": 1},
            ],
        )
        self.assertEqual(result["labels"], ["2025 Q1", "2024 Q1", "2023 Q1"])

    def test_monthly_multi(self):
        """Monthly periods should produce correct labels."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[
                {"year": 2024, "month": 6},
                {"year": 2023, "month": 6},
            ],
        )
        self.assertEqual(result["labels"], ["2024-06", "2023-06"])

    def test_brand_comparison_multi(self):
        """Brand comparison should have revenues list matching period count."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[{"year": 2025}, {"year": 2024}, {"year": 2023}],
        )
        brands = result["brand_comparison"]
        self.assertGreater(len(brands), 0)
        for b in brands:
            self.assertEqual(len(b["revenues"]), 3)
            self.assertEqual(len(b["qtys"]), 3)
            self.assertIn("change", b)

    def test_channel_comparison_multi(self):
        """Channel comparison should have revenues list matching period count."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[{"year": 2024}, {"year": 2023}],
        )
        channels = result["channel_comparison"]
        self.assertGreater(len(channels), 0)
        for c in channels:
            self.assertEqual(len(c["revenues"]), 2)
            self.assertEqual(len(c["qtys"]), 2)

    def test_changes_first_vs_last(self):
        """Changes should compare first period vs last period."""
        result = pc.compute_multi_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
            periods=[{"year": 2025}, {"year": 2024}, {"year": 2023}],
        )
        changes = result["changes"]
        # First (2025) vs Last (2023) — should be "up" since 2025 > 2023
        self.assertEqual(changes["revenue_thb"]["direction"], "up")

    def test_too_few_periods_raises(self):
        """Less than 2 periods should raise ValueError."""
        with self.assertRaises(ValueError):
            pc.compute_multi_period_comparison(
                self.sale, self.onhand, self.master, self.grpo,
                periods=[{"year": 2024}],
            )

    def test_too_many_periods_raises(self):
        """More than 4 periods should raise ValueError."""
        with self.assertRaises(ValueError):
            pc.compute_multi_period_comparison(
                self.sale, self.onhand, self.master, self.grpo,
                periods=[{"year": y} for y in range(2020, 2026)],
            )

    def test_no_periods_raises(self):
        """None or empty periods should raise ValueError."""
        with self.assertRaises(ValueError):
            pc.compute_multi_period_comparison(
                self.sale, self.onhand, self.master, self.grpo,
                periods=None,
            )


class TestDynamicYearDefaults(unittest.TestCase):
    """Regression tests for OBJ-39: no hardcoded year defaults."""

    def setUp(self):
        self.sale = _sale_fixture()
        self.onhand = _onhand_fixture()
        self.master = _master_fixture()
        self.grpo = _grpo_fixture()

    def test_default_years_use_current_year(self):
        """compute_period_comparison with None years should use current year."""
        from datetime import datetime
        current_year = datetime.now().year
        result = pc.compute_period_comparison(
            self.sale, self.onhand, self.master, self.grpo,
        )
        self.assertEqual(result["period_a_label"], str(current_year))
        self.assertEqual(result["period_b_label"], str(current_year - 1))

    def test_no_hardcoded_2025_in_concentration_endpoint(self):
        """Verify concentration_summary endpoint uses dynamic year default."""
        import inspect
        from app.api.routes import data_analysis
        src = inspect.getsource(data_analysis.get_concentration_summary)
        self.assertNotIn("default=2025", src)
        self.assertNotIn("default=2024", src)

    def test_no_hardcoded_2025_in_period_comparison_endpoint(self):
        """Verify period_comparison endpoint uses dynamic year default."""
        import inspect
        from app.api.routes import data_analysis
        src = inspect.getsource(data_analysis.get_period_comparison)
        self.assertNotIn("default=2025", src)
        self.assertNotIn("default=2024", src)


if __name__ == "__main__":
    unittest.main()
