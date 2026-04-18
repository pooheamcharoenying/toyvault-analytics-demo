"""Tests for item_detail.compute_item_location_detail()."""
from __future__ import annotations
import unittest
import tests.conftest  # noqa: F401 — must be imported first to set up mocks

import pandas as pd
from app.utils.item_detail import compute_item_location_detail


class TestItemLocationDetail(unittest.TestCase):
    """Tests for compute_item_location_detail()."""

    def _make_fixtures(self):
        """Create small test DataFrames."""
        df_master = pd.DataFrame({
            "ItemCode": ["A001", "A002", "B001"],
            "ItemName": ["Widget Alpha", "Widget Beta", "Gadget One"],
            "GroupName": ["BrandA", "BrandA", "BrandB"],
            "Price": [100.0, 200.0, 50.0],
        })
        df_onhand = pd.DataFrame({
            "ItemCode": ["A001", "A001", "A001", "B001"],
            "WhsCode": ["WH01", "WH02", "WH03", "WH01"],
            "OnHand": [50, 30, 0, 100],
        })
        df_sale = pd.DataFrame({
            "DocEntry": [1, 2, 3, 4, 5],
            "ItemCode": ["A001", "A001", "A001", "A001", "B001"],
            "DocDate": ["2024-01-15", "2024-02-10", "2024-03-05", "2024-01-20", "2024-01-15"],
            "WhsCode": ["WH01", "WH01", "WH02", "WH03", "WH01"],
            "Quantity": [10, 20, 5, 15, 8],
            "LineTotal": [1000, 2000, 1000, 1500, 400],
            "GroupName": ["Shop", "Shop", "Online", "Shop", "Shop"],
        })
        df_whs = pd.DataFrame({
            "WhsCode": ["WH01", "WH02", "WH03"],
            "WhsName": ["Main Warehouse", "Shop Downtown", "Online Fulfillment"],
        })
        return df_sale, df_onhand, df_master, df_whs

    def test_basic_structure(self):
        """Result has expected top-level keys."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        self.assertTrue(result["found"])
        self.assertIn("item_info", result)
        self.assertIn("locations", result)

    def test_item_info_fields(self):
        """Item info has all required fields."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        info = result["item_info"]
        self.assertEqual(info["item_code"], "A001")
        self.assertEqual(info["item_name"], "Widget Alpha")
        self.assertEqual(info["brand"], "BrandA")
        self.assertEqual(info["master_price"], 100.0)

    def test_location_breakdown(self):
        """Each location has onhand and sold fields."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        locs = result["locations"]
        self.assertGreater(len(locs), 0)
        for loc in locs:
            self.assertIn("whs_code", loc)
            self.assertIn("whs_name", loc)
            self.assertIn("onhand_qty", loc)
            self.assertIn("onhand_thb", loc)
            self.assertIn("lifetime_sold_qty", loc)
            self.assertIn("lifetime_sold_thb", loc)

    def test_sorted_by_onhand_desc(self):
        """Locations sorted by on-hand qty descending."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        locs = result["locations"]
        for i in range(len(locs) - 1):
            self.assertGreaterEqual(locs[i]["onhand_qty"], locs[i + 1]["onhand_qty"])

    def test_totals_match_sum(self):
        """Total on-hand and sold = sum of per-location values."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        info = result["item_info"]
        locs = result["locations"]
        self.assertAlmostEqual(
            info["total_onhand_qty"],
            sum(l["onhand_qty"] for l in locs),
            places=2,
        )
        self.assertAlmostEqual(
            info["total_sold_qty"],
            sum(l["lifetime_sold_qty"] for l in locs),
            places=2,
        )

    def test_onhand_thb_uses_master_price(self):
        """On-hand THB = qty x master price."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        for loc in result["locations"]:
            expected_thb = loc["onhand_qty"] * 100.0  # A001 master price = 100
            self.assertAlmostEqual(loc["onhand_thb"], expected_thb, places=2)

    def test_whs_names_resolved(self):
        """Warehouse names come from whs_code lookup."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        names = {loc["whs_name"] for loc in result["locations"]}
        self.assertIn("Main Warehouse", names)

    def test_nonexistent_item(self):
        """Nonexistent item returns found=False."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("ZZZZZ", df_sale, df_onhand, df_master, df_whs)
        self.assertFalse(result["found"])
        self.assertEqual(result["locations"], [])

    def test_item_with_sales_no_onhand(self):
        """Item sold at a location but no current on-hand still shows in locations."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        # WH03 has 0 on-hand but has sales — it should appear with onhand_qty=0
        wh03 = [l for l in result["locations"] if l["whs_code"] == "WH03"]
        self.assertEqual(len(wh03), 1)
        self.assertEqual(wh03[0]["onhand_qty"], 0)
        self.assertGreater(wh03[0]["lifetime_sold_qty"], 0)

    def test_empty_dataframes(self):
        """Empty input doesn't crash."""
        empty_df = pd.DataFrame()
        df_master = pd.DataFrame({
            "ItemCode": ["A001"],
            "ItemName": ["Widget"],
            "GroupName": ["Brand"],
            "Price": [100],
        })
        result = compute_item_location_detail("A001", empty_df, empty_df, df_master, empty_df)
        self.assertFalse(result["found"])

    def test_sale_dedup(self):
        """Duplicate sales are not double-counted."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        # Duplicate a row
        dup_row = df_sale.iloc[[0]].copy()
        df_sale_duped = pd.concat([df_sale, dup_row], ignore_index=True)
        result_clean = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        result_duped = compute_item_location_detail("A001", df_sale_duped, df_onhand, df_master, df_whs)
        self.assertEqual(
            result_clean["item_info"]["total_sold_qty"],
            result_duped["item_info"]["total_sold_qty"],
        )


class TestItemABCDE(unittest.TestCase):
    """Tests for ABCDE classification in item detail (OBJ-83)."""

    def _make_fixtures(self):
        df_master = pd.DataFrame({
            "ItemCode": ["A001", "A002", "B001"],
            "ItemName": ["Widget Alpha", "Widget Beta", "Gadget One"],
            "GroupName": ["BrandA", "BrandA", "BrandB"],
            "Price": [100.0, 200.0, 50.0],
        })
        df_onhand = pd.DataFrame({
            "ItemCode": ["A001", "A001", "B001"],
            "WhsCode": ["WH01", "WH02", "WH01"],
            "OnHand": [50, 30, 100],
        })
        df_sale = pd.DataFrame({
            "DocEntry": [1, 2, 3, 4, 5],
            "ItemCode": ["A001", "A001", "A002", "A001", "B001"],
            "DocDate": ["2024-01-15", "2024-02-10", "2024-03-05", "2024-01-20", "2024-01-15"],
            "WhsCode": ["WH01", "WH01", "WH02", "WH01", "WH01"],
            "Quantity": [10, 20, 5, 15, 8],
            "LineTotal": [1000, 2000, 1000, 1500, 400],
            "GroupName": ["Shop", "Shop", "Online", "Shop", "Shop"],
        })
        df_whs = pd.DataFrame({
            "WhsCode": ["WH01", "WH02"],
            "WhsName": ["Main Warehouse", "Shop Downtown"],
        })
        return df_sale, df_onhand, df_master, df_whs

    def test_abcde_fields_present(self):
        """item_info must have abcde_class_in_brand and abcde_class_overall."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        self.assertTrue(result["found"])
        self.assertIn("abcde_class_in_brand", result["item_info"])
        self.assertIn("abcde_class_overall", result["item_info"])

    def test_abcde_valid_values(self):
        """ABCDE class must be A, B, C, D, or E."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        for field in ("abcde_class_in_brand", "abcde_class_overall"):
            self.assertIn(result["item_info"][field], ("A", "B", "C", "D", "E"))

    def test_top_revenue_item_is_class_a(self):
        """The highest-revenue item in its brand should be class A."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        # A001 has revenue 4500 (1000+2000+1500), A002 has 1000 — A001 is top in BrandA
        result = compute_item_location_detail("A001", df_sale, df_onhand, df_master, df_whs)
        self.assertEqual(result["item_info"]["abcde_class_in_brand"], "A")

    def test_not_found_returns_no_abcde(self):
        """If item not found, no abcde fields in response."""
        df_sale, df_onhand, df_master, df_whs = self._make_fixtures()
        result = compute_item_location_detail("NOTEXIST", df_sale, df_onhand, df_master, df_whs)
        self.assertFalse(result["found"])
        self.assertNotIn("abcde_class_in_brand", result.get("item_info", {}))


if __name__ == "__main__":
    unittest.main()
