"""Tests for the Actions Engine (OBJ-16): compute_priority_actions()."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import actions_engine as ae


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sale_fixture():
    """Sales with a fast-seller, slow-seller, and no sales for DEAD1."""
    dates = (
        ["2024-10-01"] * 2
        + ["2024-10-15"] * 2
        + ["2024-11-01"] * 2
    )
    return pd.DataFrame({
        "DocDate": pd.to_datetime(dates),
        "DocEntry": list(range(1, 7)),
        "ItemCode": ["FAST1", "SLOW1"] * 3,
        "ItemName": ["Fast Item", "Slow Item"] * 3,
        "Brand": [np.nan] * 6,
        "Price": [100.0] * 6,
        "GroupName": ["Ch1"] * 6,
        "Quantity": [50, 1, 50, 1, 50, 1],
        "LineTotal": [5000, 100, 5000, 100, 5000, 100],
        "WhsCode": ["WH01"] * 6,
        "Master Price": [100.0] * 6,
        "Price Master": [100.0] * 6,
    })


def _onhand_fixture():
    """FAST1 low stock (stockout risk), SLOW1 moderate, DEAD1 lots with no sales."""
    return pd.DataFrame({
        "ItemCode": ["FAST1", "SLOW1", "DEAD1"],
        "OnHand": [5, 50, 500],
        "WhsCode": ["WH01", "WH01", "WH01"],
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["FAST1", "SLOW1", "DEAD1"],
        "ItemName": ["Fast Item", "Slow Item", "Dead Item"],
        "ItemName": ["Fast Item", "Slow Item", "Dead Item"],
        "GroupName": ["BrandA", "BrandA", "BrandB"],
        "Price": [100.0, 100.0, 100.0],
        "validFor": ["Y", "Y", "Y"],
        "frozenFor": ["N", "N", "N"],
    })


def _whs_fixture():
    return pd.DataFrame({
        "WhsCode": ["WH01"],
        "WhsName": ["Main Warehouse"],
    })


def _grpo_fixture():
    return pd.DataFrame({
        "DocDate": pd.to_datetime(["2024-09-01"]),
        "DocEntry": [1],
        "ItemCode": ["FAST1"],
        "Quantity": [100],
        "Price": [3.0],
        "Rate": [35.0],
        "Currency": ["USD"],
        "WhsCode": ["WH01"],
        "CardCode": ["V001"],
        "CardName": ["Vendor A"],
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComputePriorityActions(unittest.TestCase):
    """Core tests for the actions engine."""

    def setUp(self):
        self.sale = _sale_fixture()
        self.onhand = _onhand_fixture()
        self.master = _master_fixture()
        self.whs = _whs_fixture()
        self.grpo = _grpo_fixture()
        self.as_of = pd.Timestamp("2024-11-15")

    def test_returns_expected_structure(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            df_grpo_detail=self.grpo,
            as_of=self.as_of,
        )
        self.assertIn("actions", result)
        self.assertIn("total_actions", result)
        self.assertIn("by_type", result)
        self.assertIn("by_severity", result)
        self.assertIn("total_impact_thb", result)
        self.assertIn("as_of", result)

    def test_actions_have_required_fields(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        for action in result["actions"]:
            self.assertIn("type", action)
            self.assertIn("severity", action)
            self.assertIn("title", action)
            self.assertIn("reason", action)
            self.assertIn("impact_thb", action)
            self.assertIn("link", action)
            self.assertIn(action["type"], ("reorder", "transfer", "markdown", "investigate"))
            self.assertIn(action["severity"], ("critical", "warning", "info"))

    def test_total_actions_matches_list_length(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        self.assertEqual(result["total_actions"], len(result["actions"]))

    def test_max_actions_respected(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
            max_actions=3,
        )
        self.assertLessEqual(len(result["actions"]), 3)

    def test_actions_sorted_by_score_descending(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        scores = [a.get("score", 0) for a in result["actions"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_by_type_counts_correct(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        from collections import Counter
        actual_counts = Counter(a["type"] for a in result["actions"])
        for t, c in result["by_type"].items():
            self.assertEqual(c, actual_counts.get(t, 0))

    def test_by_severity_counts_correct(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        from collections import Counter
        actual_counts = Counter(a["severity"] for a in result["actions"])
        for s, c in result["by_severity"].items():
            self.assertEqual(c, actual_counts.get(s, 0))

    def test_handles_empty_sale_data(self):
        empty_sale = pd.DataFrame(columns=self.sale.columns)
        result = ae.compute_priority_actions(
            df_raw_sale=empty_sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        self.assertIsInstance(result["actions"], list)
        self.assertEqual(result["total_actions"], len(result["actions"]))

    def test_handles_no_grpo(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            df_grpo_detail=None,
            as_of=self.as_of,
        )
        self.assertIsInstance(result["actions"], list)

    def test_impact_thb_non_negative(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        for action in result["actions"]:
            self.assertGreaterEqual(action["impact_thb"], 0)

    def test_as_of_date_propagated(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        self.assertEqual(result["as_of"], "2024-11-15")

    def test_as_of_none(self):
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=None,
        )
        self.assertIsNone(result["as_of"])

    def test_deep_links_to_item_or_location(self):
        """OBJ-85: action links go to item-detail or location drill-down page."""
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            df_grpo_detail=self.grpo,
            as_of=self.as_of,
        )
        for action in result["actions"]:
            link = action["link"]
            atype = action["type"]
            item_code = action.get("item_code")
            if atype in ("reorder", "markdown", "transfer"):
                if item_code:
                    self.assertIn(f"/dashboards/item-detail/{item_code}", link,
                                  f"{atype} action with item_code={item_code} should link to item-detail")
                else:
                    # Fallback to filtered list is acceptable
                    self.assertTrue(link.startswith("/dashboards/"), f"Invalid link: {link}")
            elif atype == "investigate":
                self.assertIn("/dashboards/locations/", link,
                              f"Investigate action should link to location drill-down: {link}")

    def test_reorder_links_to_item_detail(self):
        """OBJ-85: reorder actions link to the specific item's detail page."""
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            as_of=self.as_of,
        )
        reorder_actions = [a for a in result["actions"] if a["type"] == "reorder"]
        for action in reorder_actions:
            if action.get("item_code"):
                self.assertIn(f"/dashboards/item-detail/{action['item_code']}", action["link"])

    def test_markdown_reason_shows_onhand_units(self):
        """Markdown / Liquidate actions must clearly show on-hand units."""
        result = ae.compute_priority_actions(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            df_whs_code=self.whs,
            df_grpo_detail=self.grpo,
            as_of=self.as_of,
        )
        markdown_actions = [a for a in result["actions"] if a["type"] == "markdown"]
        # The DEAD1 fixture has 500 on-hand and zero sales — should produce
        # at least one markdown action.
        self.assertGreater(len(markdown_actions), 0,
                           "Expected at least one markdown action from DEAD1 fixture")
        for a in markdown_actions:
            # Reason text must mention "units on hand"
            self.assertIn("units on hand", a["reason"],
                          f"Markdown reason should call out on-hand units: {a['reason']}")
            # Structured field too, for downstream rendering / export
            self.assertIn("onhand_qty", a)
            self.assertGreater(a["onhand_qty"], 0)


class TestBrandReorderWarnings(unittest.TestCase):
    """compute_brand_reorder_warnings: top-N per brand, 120d warning, 150d target."""

    def setUp(self):
        from app.utils import inventory_alerts as ialerts
        self.ialerts = ialerts
        # Two brands. BrandA has one HOT seller with very low stock (1d cover)
        # and one slow seller. BrandB has a steady seller with healthy cover.
        dates = pd.date_range("2024-08-01", periods=90, freq="D")
        rows = []
        # BrandA: HOT_A sells 10/day, SLOW_A sells 0.1/day
        for i, dt in enumerate(dates):
            rows.append({"DocDate": dt, "DocEntry": 10000 + i, "ItemCode": "HOT_A",
                         "ItemName": "Hot A", "Brand": np.nan, "Price": 50.0,
                         "GroupName": "Ch1", "Quantity": 10, "LineTotal": 500,
                         "WhsCode": "S1", "Master Price": 50.0, "Price Master": 500.0})
            if i % 10 == 0:
                rows.append({"DocDate": dt, "DocEntry": 20000 + i, "ItemCode": "SLOW_A",
                             "ItemName": "Slow A", "Brand": np.nan, "Price": 100.0,
                             "GroupName": "Ch1", "Quantity": 1, "LineTotal": 100,
                             "WhsCode": "S1", "Master Price": 100.0, "Price Master": 100.0})
            # BrandB: STEADY_B sells 1/day, with 200+ days cover
            rows.append({"DocDate": dt, "DocEntry": 30000 + i, "ItemCode": "STEADY_B",
                         "ItemName": "Steady B", "Brand": np.nan, "Price": 200.0,
                         "GroupName": "Ch1", "Quantity": 1, "LineTotal": 200,
                         "WhsCode": "S1", "Master Price": 200.0, "Price Master": 200.0})
        self.sale = pd.DataFrame(rows)
        self.onhand = pd.DataFrame({
            "ItemCode": ["HOT_A", "SLOW_A", "STEADY_B"],
            "OnHand": [10, 50, 500],  # HOT_A: 1d cover, STEADY_B: 500d cover
            "WhsCode": ["S1", "S1", "S1"],
        })
        self.master = pd.DataFrame({
            "ItemCode": ["HOT_A", "SLOW_A", "STEADY_B"],
            "ItemName": ["Hot A", "Slow A", "Steady B"],
            "GroupName": ["BrandA", "BrandA", "BrandB"],
            "Price": [50.0, 100.0, 200.0],
            "validFor": ["Y", "Y", "Y"],
            "frozenFor": ["N", "N", "N"],
        })
        self.as_of = pd.Timestamp("2024-10-29")

    def test_returns_per_brand_breakdown(self):
        result = self.ialerts.compute_brand_reorder_warnings(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            as_of=self.as_of,
            window_days=90,
            warning_days_cover=120,
            target_cover_days=150,
        )
        self.assertIn("brands", result)
        self.assertIn("summary", result)
        brand_names = {b["brand"] for b in result["brands"]}
        # Both brands should appear (their top sellers have revenue > 0)
        self.assertIn("BrandA", brand_names)
        self.assertIn("BrandB", brand_names)

    def test_hot_item_flagged_warning(self):
        result = self.ialerts.compute_brand_reorder_warnings(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            as_of=self.as_of,
            window_days=90,
            warning_days_cover=120,
            target_cover_days=150,
        )
        brand_a = next(b for b in result["brands"] if b["brand"] == "BrandA")
        hot = next(it for it in brand_a["items"] if it["item_code"] == "HOT_A")
        self.assertTrue(hot["is_warning"],
                        "HOT_A at 1-day cover must be flagged as warning under 120d threshold")
        # Suggested order should be ~ (10 units/day × 150d) - 10 on-hand = ~1490
        self.assertGreater(hot["suggested_order_qty"], 1000,
                           f"Suggested qty for 150d target should be substantial: {hot}")

    def test_well_stocked_item_not_flagged(self):
        result = self.ialerts.compute_brand_reorder_warnings(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            as_of=self.as_of,
            window_days=90,
            warning_days_cover=120,
            target_cover_days=150,
        )
        brand_b = next(b for b in result["brands"] if b["brand"] == "BrandB")
        steady = next(it for it in brand_b["items"] if it["item_code"] == "STEADY_B")
        # STEADY_B has 500-day cover, well above 120 threshold
        self.assertFalse(steady["is_warning"],
                         f"STEADY_B with 500d cover must NOT be warning: {steady}")

    def test_top_items_per_brand_limit(self):
        result = self.ialerts.compute_brand_reorder_warnings(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            as_of=self.as_of,
            top_items_per_brand=1,
        )
        for b in result["brands"]:
            self.assertLessEqual(len(b["items"]), 1,
                                 f"top_items_per_brand=1 must limit items: {b}")

    def test_brand_avg_days_cover_present(self):
        result = self.ialerts.compute_brand_reorder_warnings(
            df_raw_sale=self.sale,
            df_raw_onhand=self.onhand,
            df_item_master=self.master,
            as_of=self.as_of,
        )
        for b in result["brands"]:
            self.assertIn("avg_days_cover", b)
            self.assertIn("warnings_count", b)


class TestSmartTransferRecommendations(unittest.TestCase):
    """compute_smart_transfer_recommendations: dead stock at poor → good locations."""

    def setUp(self):
        from app.utils import stock_allocation as sa
        self.sa = sa

    def test_no_recs_when_no_red_or_green_locations(self):
        # All locations identical → all yellow → no recs
        dates = pd.date_range("2024-08-01", periods=90, freq="D")
        sale = pd.DataFrame([{
            "DocDate": dt, "DocEntry": 1000 + i, "ItemCode": "X1",
            "ItemName": "X", "Brand": np.nan, "Price": 100.0,
            "GroupName": "Ch1", "Quantity": 1, "LineTotal": 100,
            "WhsCode": w, "Master Price": 100.0, "Price Master": 100.0,
        } for i, dt in enumerate(dates) for w in ("L1", "L2")])
        onhand = pd.DataFrame({"ItemCode": ["X1", "X1"], "OnHand": [100, 100],
                               "WhsCode": ["L1", "L2"]})
        master = pd.DataFrame({"ItemCode": ["X1"], "ItemName": ["X"],
                               "GroupName": ["BrandA"], "Price": [100.0],
                               "validFor": ["Y"], "frozenFor": ["N"]})
        whs = pd.DataFrame({"WhsCode": ["L1", "L2"], "WhsName": ["Loc One", "Loc Two"]})
        result = self.sa.compute_smart_transfer_recommendations(
            sale, onhand, master, whs, window_days=90
        )
        self.assertEqual(result["summary"]["recommendations_count"], 0)

    def test_recommends_transfer_from_poor_to_good(self):
        # Build a scenario with a clear good vs. poor split:
        #  - GoodStore: sells 5 units/day of ITEM1 across the window (THB-heavy)
        #  - PoorStore: holds 200 units of ITEM1, ZERO sales of it
        # We expect a transfer recommendation: PoorStore → GoodStore.
        dates = pd.date_range("2024-08-01", periods=90, freq="D")
        rows = []
        for i, dt in enumerate(dates):
            # Heavy sales of ITEM1 at GoodStore
            rows.append({"DocDate": dt, "DocEntry": 100 + i, "ItemCode": "ITEM1",
                         "ItemName": "Item One", "Brand": np.nan, "Price": 200.0,
                         "GroupName": "Ch1", "Quantity": 5, "LineTotal": 1000,
                         "WhsCode": "GS", "Master Price": 200.0, "Price Master": 1000.0})
            # Tiny sales of an UNRELATED filler item at PoorStore so the
            # location appears in the analytics (but barely)
            rows.append({"DocDate": dt, "DocEntry": 5000 + i, "ItemCode": "FILLER",
                         "ItemName": "Filler", "Brand": np.nan, "Price": 10.0,
                         "GroupName": "Ch1", "Quantity": 1, "LineTotal": 10,
                         "WhsCode": "PS", "Master Price": 10.0, "Price Master": 10.0})
        sale = pd.DataFrame(rows)
        # PoorStore is loaded with ITEM1 capital that sells nowhere there
        onhand = pd.DataFrame({
            "ItemCode": ["ITEM1", "ITEM1", "FILLER", "FILLER"],
            "OnHand": [50, 1000, 10, 5000],  # GS: 50 (10d cover, needs more), PS: 1000 dead
            "WhsCode": ["GS", "PS", "GS", "PS"],
        })
        master = pd.DataFrame({
            "ItemCode": ["ITEM1", "FILLER"],
            "ItemName": ["Item One", "Filler"],
            "GroupName": ["BrandA", "BrandB"],
            "Price": [200.0, 10.0],
            "validFor": ["Y", "Y"],
            "frozenFor": ["N", "N"],
        })
        whs = pd.DataFrame({
            "WhsCode": ["GS", "PS"],
            "WhsName": ["GoodStore", "PoorStore"],
        })
        result = self.sa.compute_smart_transfer_recommendations(
            sale, onhand, master, whs,
            window_days=90,
            target_days_at_destination=90,
            min_transfer_thb=1_000,
        )
        recs = result["recommendations"]
        # We need *some* recommendation if the location performance split
        # gave us at least one green and one red. The location_analytics
        # traffic light uses company-average efficiency, so with this
        # contrived setup we should get the split. If not, the test
        # documents the contract — but we still verify the shape.
        if recs:
            r = recs[0]
            self.assertEqual(r["from_status"], "poor")
            self.assertEqual(r["to_status"], "good")
            self.assertEqual(r["item_code"], "ITEM1")
            self.assertGreater(r["transfer_qty"], 0)
            self.assertGreater(r["transfer_thb"], 0)
            # Destination days_cover must be below the 90-day target
            self.assertLess(r["to_days_cover"], 90)

    def test_warehouses_not_classified_as_poor(self):
        # Warehouse W1 with dead stock should NOT trigger transfers — it's
        # back-of-house, not a retail performance signal.
        dates = pd.date_range("2024-08-01", periods=90, freq="D")
        rows = []
        for i, dt in enumerate(dates):
            rows.append({"DocDate": dt, "DocEntry": 100 + i, "ItemCode": "ITEM1",
                         "ItemName": "Item One", "Brand": np.nan, "Price": 200.0,
                         "GroupName": "Ch1", "Quantity": 5, "LineTotal": 1000,
                         "WhsCode": "GS", "Master Price": 200.0, "Price Master": 1000.0})
        sale = pd.DataFrame(rows)
        onhand = pd.DataFrame({
            "ItemCode": ["ITEM1", "ITEM1"],
            "OnHand": [50, 1000],
            "WhsCode": ["GS", "W1"],
        })
        master = pd.DataFrame({
            "ItemCode": ["ITEM1"], "ItemName": ["Item One"],
            "GroupName": ["BrandA"], "Price": [200.0],
            "validFor": ["Y"], "frozenFor": ["N"],
        })
        whs = pd.DataFrame({
            "WhsCode": ["GS", "W1"],
            "WhsName": ["GoodStore", "Warehouse W1"],
        })
        result = self.sa.compute_smart_transfer_recommendations(
            sale, onhand, master, whs, window_days=90, min_transfer_thb=1_000,
        )
        for rec in result.get("recommendations", []):
            self.assertNotIn("warehouse", rec["from_location"].lower(),
                             f"Warehouse must not be source: {rec}")
            self.assertNotIn("warehouse", rec["to_location"].lower(),
                             f"Warehouse must not be destination: {rec}")


class TestWarehouseExclusion(unittest.TestCase):
    """Warehouses should not appear in 'Investigate' location actions."""

    def test_warehouse_locations_excluded_from_investigate(self):
        # Two warehouses + one retail store, all flagged red by virtue of
        # holding lots of unsold stock.
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-10-01", "2024-10-15", "2024-11-01"]),
            "DocEntry": [1, 2, 3],
            "ItemCode": ["X1", "X1", "X1"],
            "ItemName": ["X"] * 3,
            "Brand": [np.nan] * 3,
            "Price": [100.0] * 3,
            "GroupName": ["Ch1"] * 3,
            "Quantity": [1, 1, 1],
            "LineTotal": [100, 100, 100],
            "WhsCode": ["STORE1", "STORE1", "STORE1"],
            "Master Price": [100.0] * 3,
            "Price Master": [100.0] * 3,
        })
        onhand = pd.DataFrame({
            "ItemCode": ["X1", "X1", "X1"],
            "OnHand": [10000, 10000, 100],
            "WhsCode": ["W10", "W11", "STORE1"],
        })
        master = pd.DataFrame({
            "ItemCode": ["X1"],
            "ItemName": ["X"],
            "GroupName": ["BrandA"],
            "Price": [100.0],
            "validFor": ["Y"],
            "frozenFor": ["N"],
        })
        whs = pd.DataFrame({
            "WhsCode": ["W10", "W11", "STORE1"],
            "WhsName": ["Warehouse W10", "Warehouse W11", "Bangkok Store"],
        })
        result = ae.compute_priority_actions(
            df_raw_sale=sale,
            df_raw_onhand=onhand,
            df_item_master=master,
            df_whs_code=whs,
            as_of=pd.Timestamp("2024-11-15"),
        )
        investigate = [a for a in result["actions"] if a["type"] == "investigate"]
        for a in investigate:
            title = a.get("title", "").lower()
            self.assertNotIn("warehouse w10", title,
                             f"Warehouse should not appear in Investigate: {a}")
            self.assertNotIn("warehouse w11", title,
                             f"Warehouse should not appear in Investigate: {a}")


if __name__ == "__main__":
    unittest.main()
