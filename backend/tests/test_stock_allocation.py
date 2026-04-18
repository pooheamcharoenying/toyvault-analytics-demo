"""Tests for stock allocation optimization and transfer analysis.

Tests cover:
1. compute_stock_allocation() — overstocked/understocked identification, transfer recs
2. compute_transfer_history() — TR IN/TR OUT analysis, net flows, top items
3. compute_rebalancing_summary() — high-level opportunity, location balance, brand opps
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import stock_allocation as sa


# ---------------------------------------------------------------------------
# Test fixtures — multi-location data with varied sales velocity
# ---------------------------------------------------------------------------

def _whs_code_fixture():
    return pd.DataFrame({
        "WhsCode": ["WH01", "WH02", "WH03"],
        "WhsName": ["Main Warehouse", "Bangkok Store", "Chiang Mai"],
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1", "B2", "C1"],
        "GroupName": ["BrandA", "BrandA", "BrandB", "BrandB", "BrandC"],
        "ItemName": ["Item A1", "Item A2", "Item B1", "Item B2", "Item C1"],
        "Price": [100.0, 200.0, 150.0, 80.0, 50.0],
    })


def _onhand_fixture():
    """On-hand at 3 locations.  A1 is overstocked at WH01 but understocked at WH02."""
    return pd.DataFrame({
        "ItemCode": ["A1", "A1", "A1", "A2", "B1", "B1", "C1"],
        "OnHand":   [ 500,   5,   200,   50,   100,   10,   80],
        "WhsCode":  ["WH01", "WH02", "WH03", "WH01", "WH01", "WH02", "WH03"],
    })


def _sale_fixture():
    """Sales: A1 sells fast at WH02 but slow at WH01.  B1 sells only at WH01."""
    rows = []
    doc = 1
    # A1 sells fast at WH02 over 90 days
    for day in range(1, 90, 3):
        rows.append({
            "DocDate": pd.Timestamp("2024-01-01") + pd.Timedelta(days=day),
            "DocEntry": doc, "ItemCode": "A1", "ItemName": "Item A1",
            "Brand": np.nan, "Price": 100.0, "GroupName": "Ch1",
            "Quantity": 10, "LineTotal": 1000.0,
            "WhsCode": "WH02", "Master Price": 100.0, "Price Master": 100.0,
        })
        doc += 1
    # A1 sells slowly at WH01
    for day in [15, 45, 75]:
        rows.append({
            "DocDate": pd.Timestamp("2024-01-01") + pd.Timedelta(days=day),
            "DocEntry": doc, "ItemCode": "A1", "ItemName": "Item A1",
            "Brand": np.nan, "Price": 100.0, "GroupName": "Ch1",
            "Quantity": 2, "LineTotal": 200.0,
            "WhsCode": "WH01", "Master Price": 100.0, "Price Master": 100.0,
        })
        doc += 1
    # B1 sells at WH01
    for day in [10, 30, 50, 70]:
        rows.append({
            "DocDate": pd.Timestamp("2024-01-01") + pd.Timedelta(days=day),
            "DocEntry": doc, "ItemCode": "B1", "ItemName": "Item B1",
            "Brand": np.nan, "Price": 150.0, "GroupName": "Ch2",
            "Quantity": 5, "LineTotal": 750.0,
            "WhsCode": "WH01", "Master Price": 150.0, "Price Master": 150.0,
        })
        doc += 1
    # C1 — zero sales anywhere (dead at WH03)
    return pd.DataFrame(rows)


def _tr_in_fixture():
    """Transfer IN data."""
    return pd.DataFrame({
        "DocEntry": [8001, 8002, 8003, 8004],
        "DocDate": pd.to_datetime(["2024-01-15", "2024-02-10", "2024-02-20", "2024-03-05"]),
        "ShipDate": pd.to_datetime(["2024-01-15", "2024-02-10", "2024-02-20", "2024-03-05"]),
        "LineNum": [0, 0, 0, 0],
        "CodeBars": ["", "", "", ""],
        "ItemCode": ["A1", "B1", "A1", "A2"],
        "ItemName": ["TR IN A1", "TR IN B1", "TR IN A1", "TR IN A2"],
        "Quantity": [50, 30, 20, 15],
        "WhsCode": ["WH02", "WH01", "WH03", "WH01"],
    })


def _tr_out_fixture():
    """Transfer OUT data (negative quantities)."""
    return pd.DataFrame({
        "DocEntry": [9001, 9002, 9003],
        "DocDate": pd.to_datetime(["2024-01-15", "2024-02-10", "2024-03-01"]),
        "ShipDate": pd.to_datetime(["2024-01-15", "2024-02-10", "2024-03-01"]),
        "LineNum": [0, 0, 0],
        "CodeBars": ["", "", ""],
        "ItemCode": ["A1", "B1", "A1"],
        "ItemName": ["TR OUT A1", "TR OUT B1", "TR OUT A1"],
        "Quantity": [-50, -30, -20],
        "WhsCode": ["WH01", "WH02", "WH01"],
    })


# ---------------------------------------------------------------------------
# Tests: compute_stock_allocation
# ---------------------------------------------------------------------------

class TestStockAllocation(unittest.TestCase):

    def _run(self, **kwargs):
        return sa.compute_stock_allocation(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            **kwargs,
        )

    def test_returns_expected_keys(self):
        result = self._run()
        for key in ["summary", "recommendations", "overstocked", "understocked"]:
            self.assertIn(key, result)

    def test_summary_has_required_fields(self):
        s = self._run()["summary"]
        for key in ["total_items", "total_locations", "transfer_recommendations", "potential_thb_savings"]:
            self.assertIn(key, s)

    def test_total_items_positive(self):
        self.assertGreater(self._run()["summary"]["total_items"], 0)

    def test_total_locations_matches_warehouses(self):
        self.assertLessEqual(self._run()["summary"]["total_locations"], 3)

    def test_overstocked_has_required_fields(self):
        result = self._run()
        if result["overstocked"]:
            row = result["overstocked"][0]
            for key in ["ItemCode", "WhsCode", "onhand_qty", "excess_qty", "excess_thb"]:
                self.assertIn(key, row)

    def test_understocked_has_required_fields(self):
        result = self._run()
        if result["understocked"]:
            row = result["understocked"][0]
            for key in ["ItemCode", "WhsCode", "onhand_qty", "deficit_qty", "deficit_thb"]:
                self.assertIn(key, row)

    def test_a1_wh01_should_be_overstocked(self):
        """A1 at WH01: 500 on hand, only 6 sold in 90 days → heavily overstocked."""
        result = self._run()
        over_a1_wh01 = [
            r for r in result["overstocked"]
            if r["ItemCode"] == "A1" and r["WhsCode"] == "WH01"
        ]
        self.assertTrue(len(over_a1_wh01) > 0, "A1 at WH01 should be overstocked")

    def test_recommendations_have_from_to(self):
        result = self._run()
        if result["recommendations"]:
            rec = result["recommendations"][0]
            for key in ["ItemCode", "from_location", "to_location", "transfer_qty", "transfer_thb"]:
                self.assertIn(key, rec)

    def test_recommendations_transfer_qty_positive(self):
        for rec in self._run()["recommendations"]:
            self.assertGreater(rec["transfer_qty"], 0)

    def test_potential_thb_savings_non_negative(self):
        self.assertGreaterEqual(self._run()["summary"]["potential_thb_savings"], 0)

    def test_brand_filter(self):
        result = self._run(brand="BrandA")
        for item in result["overstocked"]:
            self.assertEqual(item.get("Brand"), "BrandA")
        for item in result["understocked"]:
            self.assertEqual(item.get("Brand"), "BrandA")

    def test_empty_onhand_returns_empty(self):
        result = sa.compute_stock_allocation(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=pd.DataFrame(columns=["ItemCode", "OnHand", "WhsCode"]),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
        )
        self.assertEqual(result["summary"]["total_items"], 0)
        self.assertEqual(result["recommendations"], [])


# ---------------------------------------------------------------------------
# Tests: compute_transfer_history
# ---------------------------------------------------------------------------

class TestTransferHistory(unittest.TestCase):

    def _run(self, **kwargs):
        return sa.compute_transfer_history(
            df_tr_in=_tr_in_fixture(),
            df_tr_out=_tr_out_fixture(),
            df_whs_code=_whs_code_fixture(),
            df_item_master=_master_fixture(),
            **kwargs,
        )

    def test_returns_expected_keys(self):
        for key in ["summary", "location_flows", "top_items", "monthly_trend"]:
            self.assertIn(key, self._run())

    def test_summary_has_required_fields(self):
        s = self._run()["summary"]
        for key in ["total_transfers_in", "total_transfers_out", "total_items_transferred",
                     "total_qty_in", "total_qty_out", "net_qty"]:
            self.assertIn(key, s)

    def test_total_qty_in_positive(self):
        self.assertGreater(self._run()["summary"]["total_qty_in"], 0)

    def test_total_qty_out_positive(self):
        self.assertGreater(self._run()["summary"]["total_qty_out"], 0)

    def test_location_flows_have_net(self):
        flows = self._run()["location_flows"]
        self.assertGreater(len(flows), 0)
        for key in ["WhsCode", "WhsName", "qty_in", "qty_out", "net_flow", "transfer_count"]:
            self.assertIn(key, flows[0])

    def test_top_items_have_brand(self):
        items = self._run()["top_items"]
        self.assertGreater(len(items), 0)
        self.assertIn("Brand", items[0])
        self.assertIn("total_in", items[0])

    def test_monthly_trend_sorted(self):
        trend = self._run()["monthly_trend"]
        if len(trend) > 1:
            periods = [r["period"] for r in trend]
            self.assertEqual(periods, sorted(periods))

    def test_year_filter(self):
        result = self._run(year=2024)
        for entry in result["monthly_trend"]:
            self.assertTrue(entry["period"].startswith("2024"))

    def test_empty_transfers(self):
        result = sa.compute_transfer_history(
            df_tr_in=pd.DataFrame(),
            df_tr_out=pd.DataFrame(),
            df_whs_code=_whs_code_fixture(),
            df_item_master=_master_fixture(),
        )
        self.assertEqual(result["summary"]["total_transfers_in"], 0)
        self.assertEqual(result["location_flows"], [])

    def test_net_qty_equals_in_minus_out(self):
        s = self._run()["summary"]
        self.assertEqual(s["net_qty"], s["total_qty_in"] - s["total_qty_out"])

    def test_items_transferred_count(self):
        """A1, B1, A2 are transferred = 3 unique items."""
        self.assertEqual(self._run()["summary"]["total_items_transferred"], 3)


# ---------------------------------------------------------------------------
# Tests: compute_rebalancing_summary
# ---------------------------------------------------------------------------

class TestRebalancingSummary(unittest.TestCase):

    def _run(self, **kwargs):
        return sa.compute_rebalancing_summary(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            **kwargs,
        )

    def test_returns_expected_keys(self):
        for key in ["summary", "location_balance", "brand_opportunities"]:
            self.assertIn(key, self._run())

    def test_summary_has_required_fields(self):
        s = self._run()["summary"]
        for key in ["total_surplus_thb", "total_deficit_thb", "rebalanceable_thb",
                     "surplus_locations", "deficit_locations", "items_to_move"]:
            self.assertIn(key, s)

    def test_rebalanceable_leq_min_surplus_deficit(self):
        s = self._run()["summary"]
        self.assertLessEqual(
            s["rebalanceable_thb"],
            min(s["total_surplus_thb"], s["total_deficit_thb"]) + 0.01,
        )

    def test_location_balance_has_status(self):
        locs = self._run()["location_balance"]
        if locs:
            self.assertIn(locs[0]["status"], ["surplus", "deficit", "balanced"])

    def test_location_balance_has_priority(self):
        locs = self._run()["location_balance"]
        if locs:
            self.assertIn(locs[0]["priority"], ["high", "medium", "low"])

    def test_brand_opportunities_present(self):
        self.assertGreater(len(self._run()["brand_opportunities"]), 0)

    def test_brand_opp_rebalanceable_leq_min(self):
        for opp in self._run()["brand_opportunities"]:
            self.assertLessEqual(
                opp["rebalanceable_thb"],
                min(opp["surplus_thb"], opp["deficit_thb"]) + 0.01,
            )

    def test_empty_data(self):
        result = sa.compute_rebalancing_summary(
            df_raw_sale=pd.DataFrame(columns=["DocDate", "DocEntry", "ItemCode", "Quantity",
                                               "LineTotal", "WhsCode", "GroupName", "Brand",
                                               "Price", "Master Price", "Price Master", "ItemName"]),
            df_raw_onhand=pd.DataFrame(columns=["ItemCode", "OnHand", "WhsCode"]),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
        )
        self.assertEqual(result["summary"]["rebalanceable_thb"], 0)


if __name__ == "__main__":
    unittest.main()
