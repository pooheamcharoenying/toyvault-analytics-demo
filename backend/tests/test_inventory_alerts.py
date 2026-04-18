"""Tests for inventory action alerts: stockout risk, dead stock, reorder analysis."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import inventory_alerts as ialerts


# ---------------------------------------------------------------------------
# Test fixtures — richer than minimal to exercise stockout/dead stock logic
# ---------------------------------------------------------------------------

def _sale_fixture():
    """Sales data with a mix of fast-sellers, slow-sellers, and non-sellers."""
    dates = (
        ["2024-01-15"] * 3
        + ["2024-02-01"] * 3
        + ["2024-02-15"] * 3
    )
    return pd.DataFrame({
        "DocDate": pd.to_datetime(dates),
        "DocEntry": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "ItemCode": ["FAST1", "FAST1", "SLOW1", "FAST1", "FAST1", "SLOW1", "FAST1", "FAST1", "SLOW1"],
        "ItemName": ["Fast Item"] * 2 + ["Slow Item"] + ["Fast Item"] * 2 + ["Slow Item"] + ["Fast Item"] * 2 + ["Slow Item"],
        "Brand": [np.nan] * 9,
        "Price": [100.0] * 9,
        "GroupName": ["Ch1", "Ch2", "Ch1", "Ch1", "Ch2", "Ch1", "Ch1", "Ch2", "Ch1"],
        "Quantity": [10, 5, 1, 10, 5, 1, 10, 5, 1],
        "LineTotal": [1000, 500, 100, 1000, 500, 100, 1000, 500, 100],
        "WhsCode": ["WH01"] * 9,
        "Master Price": [100.0] * 9,
        "Price Master": [1000, 500, 100, 1000, 500, 100, 1000, 500, 100],  # Qty × unit price
    })


def _onhand_fixture():
    """On-hand: FAST1 has low stock (about to run out), SLOW1 has medium stock, DEAD1 has stock but no sales."""
    return pd.DataFrame({
        "ItemCode": ["FAST1", "SLOW1", "DEAD1"],
        "OnHand": [5, 50, 200],
        "WhsCode": ["WH01", "WH01", "WH01"],
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["FAST1", "SLOW1", "DEAD1"],
        "GroupName": ["BrandA", "BrandB", "BrandC"],
        "ItemName": ["Fast Item", "Slow Item", "Dead Item"],
        "Price": [100.0, 50.0, 30.0],
    })


def _grpo_fixture():
    return pd.DataFrame({
        "DocDate": pd.to_datetime(["2024-01-01", "2024-01-10", "2024-02-01"]),
        "ItemCode": ["FAST1", "DEAD1", "FAST1"],
        "Quantity": [100, 200, 50],
        "Price": [5.0, 3.0, 5.5],
        "Rate": [35.0, 35.0, 35.0],
        "Currency": ["USD", "USD", "USD"],
        "WhsCode": ["WH01", "WH01", "WH01"],
        "CardCode": ["V001", "V002", "V001"],
        "CardName": ["Vendor A", "Vendor B", "Vendor A"],
    })


# ---------------------------------------------------------------------------
# Shared helper tests
# ---------------------------------------------------------------------------

class TestBuildItemVelocity(unittest.TestCase):
    def test_returns_correct_columns(self):
        from app.utils import nichi_stock as nstk
        df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        item = ialerts._build_item_velocity(df_sale, df_onhand, window_days=90,
                                            as_of=pd.Timestamp("2024-02-28"))
        expected_cols = {"ItemCode", "Brand", "OnHand", "Master Price",
                         "onhand_thb", "sold_qty", "sold_thb", "avg_daily_qty", "days_cover"}
        self.assertTrue(expected_cols.issubset(set(item.columns)))

    def test_dead_item_has_inf_days_cover(self):
        from app.utils import nichi_stock as nstk
        df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        item = ialerts._build_item_velocity(df_sale, df_onhand, window_days=90,
                                            as_of=pd.Timestamp("2024-02-28"))
        dead = item[item["ItemCode"] == "DEAD1"]
        self.assertFalse(dead.empty, "DEAD1 should be present in result")
        self.assertEqual(float(dead.iloc[0]["days_cover"]), float("inf"))

    def test_fast_seller_has_finite_days_cover(self):
        from app.utils import nichi_stock as nstk
        df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        item = ialerts._build_item_velocity(df_sale, df_onhand, window_days=90,
                                            as_of=pd.Timestamp("2024-02-28"))
        fast = item[item["ItemCode"] == "FAST1"]
        self.assertFalse(fast.empty)
        dc = float(fast.iloc[0]["days_cover"])
        self.assertGreater(dc, 0)
        self.assertLess(dc, float("inf"))

    def test_empty_sales_returns_empty(self):
        from app.utils import nichi_stock as nstk
        empty_sale = pd.DataFrame(columns=_sale_fixture().columns)
        df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
            _sale_fixture(), _onhand_fixture(), _master_fixture()
        )
        result = ialerts._build_item_velocity(empty_sale, df_onhand, window_days=90)
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# Stockout Risk Tests
# ---------------------------------------------------------------------------

class TestStockoutRisk(unittest.TestCase):
    def test_stockout_risk_payload_structure(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50,
        )
        self.assertIn("rows", out)
        self.assertIn("summary", out)
        self.assertIn("as_of", out)
        self.assertIn("threshold_days", out)

    def test_fast_seller_appears_as_at_risk(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50,
        )
        item_codes = [r["item_code"] for r in out["rows"]]
        self.assertIn("FAST1", item_codes, "FAST1 (low stock, high velocity) should be at risk")

    def test_dead_item_not_at_risk(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50,
        )
        item_codes = [r["item_code"] for r in out["rows"]]
        self.assertNotIn("DEAD1", item_codes, "DEAD1 has no sales so no stockout risk")

    def test_rows_have_required_fields(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50,
        )
        if out["rows"]:
            row = out["rows"][0]
            for key in ["item_code", "brand", "onhand_qty", "avg_daily_qty",
                        "days_cover", "projected_stockout", "severity", "suggested_reorder_qty"]:
                self.assertIn(key, row, f"Missing key: {key}")

    def test_severity_levels_correct(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50,
        )
        for row in out["rows"]:
            self.assertIn(row["severity"], ["critical", "warning", "watch"])

    def test_summary_counts_match_rows(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50,
        )
        total = out["summary"]["total_at_risk_items"]
        self.assertEqual(total, len(out["rows"]))

    def test_empty_data_returns_empty_rows(self):
        empty_sale = _sale_fixture().iloc[:0]
        out = ialerts.compute_stockout_risk(
            empty_sale, _onhand_fixture(), _master_fixture(),
            window_days=90, stockout_threshold_days=30, top_n=10,
        )
        self.assertEqual(len(out["rows"]), 0)


# ---------------------------------------------------------------------------
# Dead Stock Tests
# ---------------------------------------------------------------------------

class TestDeadStock(unittest.TestCase):
    def test_dead_stock_payload_structure(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
        )
        self.assertIn("rows", out)
        self.assertIn("summary", out)
        self.assertIn("dead_stock_items", out["summary"])
        self.assertIn("slow_moving_items", out["summary"])
        self.assertIn("total_capital_at_risk", out["summary"])

    def test_dead_item_identified(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
        )
        dead_items = [r["item_code"] for r in out["rows"] if r["category"] == "dead"]
        self.assertIn("DEAD1", dead_items, "DEAD1 should be identified as dead stock")

    def test_fast_seller_not_dead(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
        )
        dead_items = [r["item_code"] for r in out["rows"] if r["category"] == "dead"]
        self.assertNotIn("FAST1", dead_items)

    def test_dead_stock_has_recommended_action(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
        )
        for row in out["rows"]:
            self.assertIn("recommended_action", row)
            self.assertIsInstance(row["recommended_action"], str)
            self.assertGreater(len(row["recommended_action"]), 0)

    def test_still_purchasing_flag_with_grpo(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            df_grpo_detail=_grpo_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
        )
        dead1_rows = [r for r in out["rows"] if r["item_code"] == "DEAD1"]
        self.assertTrue(len(dead1_rows) > 0)
        self.assertTrue(dead1_rows[0]["still_purchasing"],
                        "DEAD1 has GRPO activity and should be flagged as still purchasing")

    def test_brand_summary_in_output(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
        )
        self.assertIn("brands", out["summary"])
        if out["summary"]["brands"]:
            brand_row = out["summary"]["brands"][0]
            self.assertIn("brand", brand_row)
            self.assertIn("total_onhand_thb", brand_row)

    def test_capital_at_risk_positive(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
        )
        self.assertGreater(out["summary"]["total_capital_at_risk"], 0,
                           "Should have capital at risk with dead stock items")

    def test_empty_data_returns_empty(self):
        empty_sale = _sale_fixture().iloc[:0]
        out = ialerts.compute_dead_stock(
            empty_sale, _onhand_fixture(), _master_fixture(),
            window_days=180, top_n=100,
        )
        self.assertEqual(len(out["rows"]), 0)


# ---------------------------------------------------------------------------
# Reorder Analysis Tests
# ---------------------------------------------------------------------------

class TestReorderAnalysis(unittest.TestCase):
    def test_reorder_payload_structure(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
        )
        self.assertIn("rows", out)
        self.assertIn("summary", out)
        self.assertIn("lead_time_days", out)
        self.assertIn("target_cover_days", out)

    def test_fast_seller_needs_reorder(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
        )
        reorder_items = [r["item_code"] for r in out["rows"]]
        self.assertIn("FAST1", reorder_items,
                      "FAST1 with only 5 on-hand and high velocity should need reorder")

    def test_dead_item_not_in_reorder(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
        )
        reorder_items = [r["item_code"] for r in out["rows"]]
        self.assertNotIn("DEAD1", reorder_items,
                         "DEAD1 has no sales so shouldn't need reorder")

    def test_suggested_order_qty_positive(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
        )
        for row in out["rows"]:
            self.assertGreaterEqual(row["suggested_order_qty"], 0)

    def test_urgency_levels(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
        )
        for row in out["rows"]:
            self.assertIn(row["urgency"], ["critical", "urgent", "reorder"])

    def test_last_purchase_info_with_grpo(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            df_grpo_detail=_grpo_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
        )
        fast1_rows = [r for r in out["rows"] if r["item_code"] == "FAST1"]
        self.assertTrue(len(fast1_rows) > 0)
        self.assertIsNotNone(fast1_rows[0]["last_purchase_date"])
        self.assertIsNotNone(fast1_rows[0]["last_fob_thb_unit"])

    def test_total_order_thb_matches_rows(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
        )
        row_total = sum(r["suggested_order_thb"] for r in out["rows"])
        self.assertAlmostEqual(out["summary"]["total_suggested_order_thb"], row_total, places=0)

    def test_empty_data_returns_empty(self):
        empty_sale = _sale_fixture().iloc[:0]
        out = ialerts.compute_reorder_analysis(
            empty_sale, _onhand_fixture(), _master_fixture(),
            window_days=90, lead_time_days=28, target_cover_days=56, top_n=100,
        )
        self.assertEqual(len(out["rows"]), 0)


# ---------------------------------------------------------------------------
# Brand Filter Tests (OBJ-8: F-051)
# ---------------------------------------------------------------------------

class TestBrandFilterStockout(unittest.TestCase):
    """Brand filter on stockout risk narrows results to matching brand only."""

    def test_filter_by_exact_brand(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50, brand="BrandA",
        )
        for row in out["rows"]:
            self.assertIn("BrandA", row["brand"])

    def test_filter_nonexistent_brand_returns_empty(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50, brand="NoSuchBrand",
        )
        self.assertEqual(len(out["rows"]), 0)

    def test_no_brand_filter_returns_all(self):
        out = ialerts.compute_stockout_risk(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            stockout_threshold_days=60, top_n=50, brand=None,
        )
        # Without brand filter, should return whatever items are at risk
        self.assertIsInstance(out["rows"], list)


class TestBrandFilterDeadStock(unittest.TestCase):
    """Brand filter on dead stock narrows results to matching brand only."""

    def test_filter_by_brand(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
            brand="BrandC",
        )
        for row in out["rows"]:
            self.assertIn("BrandC", row["brand"])

    def test_filter_nonexistent_brand_returns_empty(self):
        out = ialerts.compute_dead_stock(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=180, top_n=100,
            brand="NoSuchBrand",
        )
        self.assertEqual(len(out["rows"]), 0)


class TestBrandFilterReorder(unittest.TestCase):
    """Brand filter on reorder analysis narrows results to matching brand."""

    def test_filter_by_brand(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
            brand="BrandA",
        )
        for row in out["rows"]:
            self.assertIn("BrandA", row["brand"])

    def test_filter_nonexistent_brand_returns_empty(self):
        out = ialerts.compute_reorder_analysis(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            as_of=pd.Timestamp("2024-02-28"), window_days=90,
            lead_time_days=28, target_cover_days=56, top_n=100,
            brand="NoSuchBrand",
        )
        self.assertEqual(len(out["rows"]), 0)


if __name__ == "__main__":
    unittest.main()
