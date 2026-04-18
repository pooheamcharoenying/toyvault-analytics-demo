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


if __name__ == "__main__":
    unittest.main()
