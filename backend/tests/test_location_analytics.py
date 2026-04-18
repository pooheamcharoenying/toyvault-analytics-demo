"""Tests for enhanced location analytics: performance rankings, trends, product mix."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import location_analytics as la


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _whs_code_fixture():
    return pd.DataFrame({
        "WhsCode": ["WH01", "WH02", "WH03"],
        "WhsName": ["Store Alpha", "Store Beta", "Store Gamma"],
    })


def _sale_fixture():
    """Multi-location sales over several months."""
    dates = (
        ["2024-01-15"] * 6
        + ["2024-02-15"] * 6
        + ["2024-03-15"] * 4
    )
    return pd.DataFrame({
        "DocDate": pd.to_datetime(dates),
        "DocEntry": list(range(1, 17)),
        "ItemCode": [
            "A1", "A2", "B1", "A1", "B1", "C1",
            "A1", "A2", "B1", "A1", "B1", "C1",
            "A1", "A2", "A1", "B1",
        ],
        "ItemName": ["Item"] * 16,
        "Brand": [np.nan] * 16,
        "Price": [100.0] * 16,
        "GroupName": ["Ch1"] * 16,
        "Quantity": [
            10, 5, 3, 8, 2, 1,
            12, 6, 4, 9, 3, 2,
            15, 7, 10, 5,
        ],
        "LineTotal": [
            1000, 500, 300, 800, 200, 100,
            1200, 600, 400, 900, 300, 200,
            1500, 700, 1000, 500,
        ],
        "WhsCode": [
            "WH01", "WH01", "WH01", "WH02", "WH02", "WH02",
            "WH01", "WH01", "WH01", "WH02", "WH02", "WH02",
            "WH01", "WH01", "WH02", "WH02",
        ],
        "Master Price": [100.0] * 16,
        "Price Master": [100.0] * 16,
    })


def _onhand_fixture():
    """On-hand across 3 locations."""
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1", "C1", "A1", "B1", "C1", "A1", "D1"],
        "OnHand": [20, 10, 50, 100, 15, 30, 5, 200, 500],
        "WhsCode": ["WH01", "WH01", "WH01", "WH01", "WH02", "WH02", "WH02", "WH03", "WH03"],
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["A1", "A2", "B1", "C1", "D1"],
        "GroupName": ["BrandA", "BrandA", "BrandB", "BrandC", "BrandD"],
        "ItemName": ["Item A1", "Item A2", "Item B1", "Item C1", "Item D1"],
        "Price": [100.0, 50.0, 80.0, 30.0, 20.0],
    })


# ---------------------------------------------------------------------------
# Location Performance Tests
# ---------------------------------------------------------------------------

class TestLocationPerformance(unittest.TestCase):
    def setUp(self):
        self.result = la.compute_location_performance(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            window_days=90,
        )

    def test_returns_dict_with_expected_keys(self):
        self.assertIn("locations", self.result)
        self.assertIn("summary", self.result)
        self.assertIn("company_avg", self.result)

    def test_locations_have_efficiency_metrics(self):
        for loc in self.result["locations"]:
            self.assertIn("revenue_per_thb_inventory", loc)
            self.assertIn("sell_through_rate", loc)
            self.assertIn("days_cover", loc)
            self.assertIn("dead_stock_pct", loc)
            self.assertIn("status", loc)
            self.assertIn("stock_turnover", loc)

    def test_locations_sorted_by_health_score_desc(self):
        scores = [loc["health_score"] for loc in self.result["locations"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_traffic_light_values_valid(self):
        for loc in self.result["locations"]:
            self.assertIn(loc["status"], ("green", "yellow", "red"))

    def test_summary_totals_match_location_sums(self):
        loc_sold = sum(loc["sold_thb"] for loc in self.result["locations"])
        self.assertAlmostEqual(
            self.result["summary"]["total_sold_thb"], loc_sold, places=0
        )

    def test_company_avg_is_positive(self):
        avg = self.result["company_avg"]["revenue_per_thb_inventory"]
        self.assertGreater(avg, 0)

    def test_stores_with_no_sales_get_zero_efficiency(self):
        # WH03 has on-hand but no sales in fixture
        locs_by_name = {loc["location"]: loc for loc in self.result["locations"]}
        if "Store Gamma" in locs_by_name:
            gamma = locs_by_name["Store Gamma"]
            self.assertEqual(gamma["revenue_per_thb_inventory"], 0.0)
            self.assertEqual(gamma["sell_through_rate"], 0.0)

    def test_year_filter_works(self):
        result = la.compute_location_performance(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            year=2024,
        )
        self.assertGreater(len(result["locations"]), 0)

    def test_year_filter_no_data_returns_empty(self):
        result = la.compute_location_performance(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            year=2000,
        )
        self.assertEqual(len(result["locations"]), 0)

    def test_dead_stock_pct_within_bounds(self):
        for loc in self.result["locations"]:
            self.assertGreaterEqual(loc["dead_stock_pct"], 0.0)
            self.assertLessEqual(loc["dead_stock_pct"], 100.0)

    def test_health_score_present_and_bounded(self):
        """Health score must be between 0 and 100 for all locations."""
        for loc in self.result["locations"]:
            self.assertIn("health_score", loc)
            self.assertGreaterEqual(loc["health_score"], 0.0)
            self.assertLessEqual(loc["health_score"], 100.0)

    def test_health_score_summary_stats(self):
        """Summary should include avg/min/max health score."""
        s = self.result["summary"]
        self.assertIn("avg_health_score", s)
        self.assertIn("max_health_score", s)
        self.assertIn("min_health_score", s)
        self.assertGreaterEqual(s["avg_health_score"], 0.0)
        self.assertLessEqual(s["avg_health_score"], 100.0)

    def test_health_score_efficient_location_scores_higher(self):
        """A location with high efficiency and low dead stock should score
        higher than a location with zero sales and all dead stock."""
        locs_by_name = {loc["location"]: loc for loc in self.result["locations"]}
        # Store Alpha has sales; Store Gamma has none (only on-hand with dead stock)
        if "Store Alpha" in locs_by_name and "Store Gamma" in locs_by_name:
            self.assertGreater(
                locs_by_name["Store Alpha"]["health_score"],
                locs_by_name["Store Gamma"]["health_score"],
            )

    def test_empty_whs_code_returns_empty(self):
        result = la.compute_location_performance(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=pd.DataFrame(),
        )
        self.assertEqual(result["locations"], [])

    # --- Optimal Inventory / Investment Analysis Tests ---

    def test_locations_have_inventory_investment_fields(self):
        """Each location must have target on-hand, gap, and status fields."""
        for loc in self.result["locations"]:
            self.assertIn("target_onhand_qty", loc)
            self.assertIn("target_onhand_thb", loc)
            self.assertIn("inventory_gap_qty", loc)
            self.assertIn("inventory_gap_thb", loc)
            self.assertIn("inventory_status", loc)

    def test_inventory_status_valid_values(self):
        """Inventory status must be one of overstocked, optimal, understocked."""
        for loc in self.result["locations"]:
            self.assertIn(loc["inventory_status"], ("overstocked", "optimal", "understocked"))

    def test_inventory_gap_is_actual_minus_target(self):
        """Gap = actual on-hand - target on-hand."""
        for loc in self.result["locations"]:
            expected_gap_thb = loc["onhand_thb"] - loc["target_onhand_thb"]
            self.assertAlmostEqual(loc["inventory_gap_thb"], expected_gap_thb, places=0)

    def test_no_sales_location_has_zero_target(self):
        """A location with zero sales should have zero target inventory
        (avg daily sales = 0 → target = 0)."""
        locs_by_name = {loc["location"]: loc for loc in self.result["locations"]}
        if "Store Gamma" in locs_by_name:
            gamma = locs_by_name["Store Gamma"]
            self.assertEqual(gamma["target_onhand_qty"], 0)
            self.assertEqual(gamma["target_onhand_thb"], 0.0)

    def test_summary_has_inventory_status_counts(self):
        """Summary must include overstocked/optimal/understocked counts and THB totals."""
        s = self.result["summary"]
        self.assertIn("overstocked_count", s)
        self.assertIn("understocked_count", s)
        self.assertIn("optimal_count", s)
        self.assertIn("total_excess_thb", s)
        self.assertIn("total_shortfall_thb", s)
        self.assertIn("target_cover_days", s)
        # Counts should sum to total locations
        total = s["overstocked_count"] + s["understocked_count"] + s["optimal_count"]
        self.assertEqual(total, s["total_locations"])

    def test_target_cover_days_parameter_affects_target(self):
        """Using a higher target_cover_days should increase target on-hand values."""
        result_30 = la.compute_location_performance(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            target_cover_days=30,
        )
        result_90 = la.compute_location_performance(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            target_cover_days=90,
        )
        # For locations with sales, target should be higher with 90 days
        for loc30 in result_30["locations"]:
            name = loc30["location"]
            loc90 = next((l for l in result_90["locations"] if l["location"] == name), None)
            if loc90 and loc30["target_onhand_qty"] > 0:
                self.assertGreater(loc90["target_onhand_qty"], loc30["target_onhand_qty"])


# ---------------------------------------------------------------------------
# Location Trends Tests
# ---------------------------------------------------------------------------

class TestLocationTrends(unittest.TestCase):
    def setUp(self):
        self.result = la.compute_location_trends(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
        )

    def test_returns_dict_with_expected_keys(self):
        self.assertIn("trends", self.result)
        self.assertIn("periods", self.result)

    def test_trends_have_monthly_data(self):
        for trend in self.result["trends"]:
            self.assertIn("location", trend)
            self.assertIn("months", trend)
            self.assertGreater(len(trend["months"]), 0)
            for m in trend["months"]:
                self.assertIn("period", m)
                self.assertIn("sold_thb", m)
                self.assertIn("sold_qty", m)

    def test_periods_sorted_chronologically(self):
        periods = self.result["periods"]
        self.assertEqual(periods, sorted(periods))

    def test_single_location_filter(self):
        result = la.compute_location_trends(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            location="Store Alpha",
        )
        self.assertEqual(len(result["trends"]), 1)
        self.assertEqual(result["trends"][0]["location"], "Store Alpha")

    def test_trends_sorted_by_total_revenue_desc(self):
        totals = [
            sum(m["sold_thb"] for m in t["months"])
            for t in self.result["trends"]
        ]
        self.assertEqual(totals, sorted(totals, reverse=True))

    def test_nonexistent_location_returns_empty(self):
        result = la.compute_location_trends(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            location="Nonexistent Store",
        )
        self.assertEqual(result["trends"], [])


# ---------------------------------------------------------------------------
# Location Product Mix Tests
# ---------------------------------------------------------------------------

class TestLocationProductMix(unittest.TestCase):
    def setUp(self):
        self.result = la.compute_location_product_mix(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            location="Store Alpha",
        )

    def test_returns_dict_with_expected_keys(self):
        for key in ("top_brands", "top_items", "non_movers", "brand_heatmap", "location"):
            self.assertIn(key, self.result)

    def test_top_brands_sorted_by_revenue(self):
        thbs = [b["sold_thb"] for b in self.result["top_brands"]]
        self.assertEqual(thbs, sorted(thbs, reverse=True))

    def test_top_items_have_required_fields(self):
        for item in self.result["top_items"]:
            self.assertIn("item_code", item)
            self.assertIn("brand", item)
            self.assertIn("sold_thb", item)
            self.assertIn("sold_qty", item)

    def test_non_movers_have_positive_onhand(self):
        for nm in self.result["non_movers"]:
            self.assertGreater(nm["onhand_qty"], 0)

    def test_brand_heatmap_has_share_and_sell_through(self):
        for bh in self.result["brand_heatmap"]:
            self.assertIn("brand", bh)
            self.assertIn("loc_share_pct", bh)
            self.assertIn("sell_through", bh)

    def test_location_name_matches_input(self):
        self.assertEqual(self.result["location"], "Store Alpha")

    def test_non_mover_total_thb_matches_sum(self):
        expected = sum(n["onhand_thb"] for n in self.result["non_movers"])
        self.assertAlmostEqual(self.result["non_mover_total_thb"], expected, places=2)

    def test_year_filter(self):
        result = la.compute_location_product_mix(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            location="Store Alpha",
            year=2024,
        )
        self.assertGreater(len(result["top_brands"]), 0)


class TestDateRangeDaysYearFilter(unittest.TestCase):
    """Regression: date_range_days must use actual data start, not Jan 1."""

    def test_mid_year_sales_start_uses_actual_data_range(self):
        """When sales start in March but year=2024, date_range_days should NOT
        count Jan-Feb (no data). Using Jan 1 inflates the range and deflates
        daily averages / efficiency metrics."""
        # Sales only in March-April 2024 (61 days of data, NOT 121 from Jan 1)
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-03-01"] * 3 + ["2024-04-30"] * 3),
            "DocEntry": list(range(1, 7)),
            "ItemCode": ["X1", "X2", "X3"] * 2,
            "ItemName": ["Item"] * 6,
            "Brand": [np.nan] * 6,
            "Price": [100.0] * 6,
            "GroupName": ["Ch1"] * 6,
            "Quantity": [10, 20, 30, 15, 25, 35],
            "LineTotal": [1000, 2000, 3000, 1500, 2500, 3500],
            "WhsCode": ["WH01"] * 6,
            "Master Price": [100.0] * 6,
            "Price Master": [100.0] * 6,
        })
        onhand = pd.DataFrame({
            "ItemCode": ["X1", "X2", "X3"],
            "OnHand": [50, 50, 50],
            "WhsCode": ["WH01"] * 3,
        })
        master = pd.DataFrame({
            "ItemCode": ["X1", "X2", "X3"],
            "GroupName": ["Brand1"] * 3,
            "ItemName": ["Item X1", "Item X2", "Item X3"],
            "Price": [100.0] * 3,
        })
        whs = pd.DataFrame({"WhsCode": ["WH01"], "WhsName": ["Store Test"]})

        result = la.compute_location_performance(
            df_raw_sale=sale, df_raw_onhand=onhand,
            df_item_master=master, df_whs_code=whs,
            year=2024, window_days=90,
        )
        loc = result["locations"][0]
        # March 1 to April 30 = 61 days (inclusive)
        # Total sold qty = 10+20+30+15+25+35 = 135, onhand_qty = 150
        # avg_daily_sales = 135 / 61 ≈ 2.21
        # days_cover = 150 / 2.21 ≈ 67.8
        # With bug (using Jan 1): 135 / 121 ≈ 1.12, days_cover = 150 / 1.12 ≈ 134 (inflated)
        self.assertLess(loc["days_cover"], 80,
                        "days_cover should reflect actual data range, not inflated from Jan 1")
        # sell_through_rate = sold_qty / onhand_qty * 100 = 135 / 150 * 100 = 90%
        self.assertAlmostEqual(loc["sell_through_rate"], 90.0, places=0)


class TestLocationABCDE(unittest.TestCase):
    """Tests for location ABCDE classification (OBJ-83 Part 2)."""

    def setUp(self):
        self.result = la.compute_location_performance(
            df_raw_sale=_sale_fixture(),
            df_raw_onhand=_onhand_fixture(),
            df_item_master=_master_fixture(),
            df_whs_code=_whs_code_fixture(),
            window_days=90,
        )

    def test_abcde_class_present_in_each_location(self):
        """Every location row must have an abcde_class field."""
        for loc in self.result["locations"]:
            self.assertIn("abcde_class", loc, f"Missing abcde_class for {loc['location']}")

    def test_abcde_class_valid_values(self):
        """abcde_class must be one of A, B, C, D, E."""
        for loc in self.result["locations"]:
            self.assertIn(loc["abcde_class"], ("A", "B", "C", "D", "E"),
                          f"Invalid abcde_class '{loc['abcde_class']}' for {loc['location']}")

    def test_at_least_one_a_location(self):
        """If there are locations with revenue, at least one should be class A."""
        locs_with_rev = [l for l in self.result["locations"] if l["sold_thb"] > 0]
        if locs_with_rev:
            a_count = sum(1 for l in self.result["locations"] if l["abcde_class"] == "A")
            self.assertGreaterEqual(a_count, 1, "No A-class location despite positive revenue")

    def test_abcde_counts_in_summary(self):
        """Summary must have abcde_a_count through abcde_e_count."""
        for tier in ("a", "b", "c", "d", "e"):
            self.assertIn(f"abcde_{tier}_count", self.result["summary"],
                          f"Missing abcde_{tier}_count in summary")

    def test_abcde_counts_sum_to_total_locations(self):
        """Sum of all ABCDE tier counts should equal total locations."""
        total = sum(
            self.result["summary"][f"abcde_{t}_count"] for t in "abcde"
        )
        self.assertEqual(total, len(self.result["locations"]))

    def test_a_locations_have_highest_revenue(self):
        """A-class locations should have higher revenue than lower-class locations."""
        locs = self.result["locations"]
        a_locs = [l for l in locs if l["abcde_class"] == "A"]
        non_a_locs = [l for l in locs if l["abcde_class"] not in ("A",)]
        if a_locs and non_a_locs:
            min_a_rev = min(l["sold_thb"] for l in a_locs)
            max_non_a_rev = max(l["sold_thb"] for l in non_a_locs)
            self.assertGreaterEqual(min_a_rev, max_non_a_rev,
                                    "A-class location has lower revenue than non-A location")


class TestOnlineWarehouseInclusion(unittest.TestCase):
    """Verify that online warehouses (like D1-SL) are NOT filtered out (OBJ-84)."""

    def test_online_warehouse_included_in_performance(self):
        """An online warehouse (D1-SL) should appear in location performance."""
        whs = pd.DataFrame({
            "WhsCode": ["WH01", "WH02", "D1-SL"],
            "WhsName": ["Store Alpha", "Store Beta", "สต็อก Shopee+ Lazada"],
        })
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-15"] * 3),
            "DocEntry": [1, 2, 3],
            "ItemCode": ["A1", "A1", "A1"],
            "ItemName": ["Item"] * 3,
            "Brand": [np.nan] * 3,
            "Price": [100.0] * 3,
            "GroupName": ["Ch1", "Ch1", "Online"],
            "Quantity": [10, 5, 8],
            "LineTotal": [1000, 500, 800],
            "WhsCode": ["WH01", "WH02", "D1-SL"],
            "Master Price": [100.0] * 3,
            "Price Master": [100.0] * 3,
        })
        oh = pd.DataFrame({
            "ItemCode": ["A1", "A1", "A1"],
            "OnHand": [20, 10, 15],
            "WhsCode": ["WH01", "WH02", "D1-SL"],
        })
        master = pd.DataFrame({
            "ItemCode": ["A1"],
            "GroupName": ["BrandA"],
            "ItemName": ["Item A1"],
            "Price": [100.0],
        })
        result = la.compute_location_performance(
            df_raw_sale=sale, df_raw_onhand=oh,
            df_item_master=master, df_whs_code=whs,
        )
        loc_names = [l["location"] for l in result["locations"]]
        # D1-SL maps to "Online (Shopee + Lazada)" via location consolidation,
        # or falls back to WhsName if consolidation mapping is unavailable.
        d1sl_found = any("Shopee" in n or "Online" in n for n in loc_names)
        self.assertTrue(d1sl_found,
                        f"Online warehouse (D1-SL) was filtered out of location performance. Found: {loc_names}")

    def test_pro_locations_are_excluded(self):
        """Locations starting with 'pro' should be excluded (but not online)."""
        whs = pd.DataFrame({
            "WhsCode": ["WH01", "PRO1", "D1-SL"],
            "WhsName": ["Store Alpha", "Pro Shop", "สต็อก Shopee+ Lazada"],
        })
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-15"] * 3),
            "DocEntry": [1, 2, 3],
            "ItemCode": ["A1", "A1", "A1"],
            "ItemName": ["Item"] * 3,
            "Brand": [np.nan] * 3,
            "Price": [100.0] * 3,
            "GroupName": ["Ch1"] * 3,
            "Quantity": [10, 5, 8],
            "LineTotal": [1000, 500, 800],
            "WhsCode": ["WH01", "PRO1", "D1-SL"],
            "Master Price": [100.0] * 3,
            "Price Master": [100.0] * 3,
        })
        oh = pd.DataFrame({
            "ItemCode": ["A1", "A1", "A1"],
            "OnHand": [20, 10, 15],
            "WhsCode": ["WH01", "PRO1", "D1-SL"],
        })
        master = pd.DataFrame({
            "ItemCode": ["A1"],
            "GroupName": ["BrandA"],
            "ItemName": ["Item A1"],
            "Price": [100.0],
        })
        result = la.compute_location_performance(
            df_raw_sale=sale, df_raw_onhand=oh,
            df_item_master=master, df_whs_code=whs,
        )
        loc_names = [l["location"] for l in result["locations"]]
        self.assertNotIn("Pro Shop", loc_names, "Pro location should be excluded")
        # D1-SL maps to "Online (Shopee + Lazada)" via consolidation
        d1sl_found = any("Shopee" in n or "Online" in n for n in loc_names)
        self.assertTrue(d1sl_found,
                        f"Online warehouse should NOT be excluded. Found: {loc_names}")
        self.assertIn("Store Alpha", loc_names)

    def test_no_hardcoded_warehouse_exclusion(self):
        """A warehouse with a non-standard code should still appear."""
        whs = pd.DataFrame({
            "WhsCode": ["WH01", "SPECIAL-1"],
            "WhsName": ["Store", "Special Warehouse"],
        })
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-15"] * 2),
            "DocEntry": [1, 2],
            "ItemCode": ["A1", "A1"],
            "ItemName": ["Item"] * 2,
            "Brand": [np.nan] * 2,
            "Price": [100.0] * 2,
            "GroupName": ["Ch1"] * 2,
            "Quantity": [10, 5],
            "LineTotal": [1000, 500],
            "WhsCode": ["WH01", "SPECIAL-1"],
            "Master Price": [100.0] * 2,
            "Price Master": [100.0] * 2,
        })
        oh = pd.DataFrame({
            "ItemCode": ["A1", "A1"],
            "OnHand": [20, 10],
            "WhsCode": ["WH01", "SPECIAL-1"],
        })
        master = pd.DataFrame({
            "ItemCode": ["A1"],
            "GroupName": ["BrandA"],
            "ItemName": ["Item A1"],
            "Price": [100.0],
        })
        result = la.compute_location_performance(
            df_raw_sale=sale, df_raw_onhand=oh,
            df_item_master=master, df_whs_code=whs,
        )
        loc_names = [l["location"] for l in result["locations"]]
        self.assertIn("Special Warehouse", loc_names)


if __name__ == "__main__":
    unittest.main()
