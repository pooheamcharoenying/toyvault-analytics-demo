"""Tests for channel analytics: channel list, channel detail, channel-location mapping."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import channel_analytics as cha


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _sale_fixture():
    """Sales across 3 channels and 4 locations."""
    return pd.DataFrame({
        "DocDate": pd.to_datetime([
            "2024-01-15", "2024-01-16", "2024-02-01", "2024-02-15",
            "2024-03-01", "2024-03-10", "2024-04-01", "2024-04-15",
            "2025-01-10", "2025-02-20",
        ]),
        "DocEntry": list(range(1, 11)),
        "ItemCode": ["ITEM1", "ITEM2", "ITEM1", "ITEM3", "ITEM2", "ITEM1", "ITEM3", "ITEM2", "ITEM1", "ITEM2"],
        "ItemName": ["Item One"] * 3 + ["Item Three"] * 2 + ["Item One"] + ["Item Three"] + ["Item Two"] * 2 + ["Item One"],
        "Brand": [np.nan] * 10,
        "Price": [100.0] * 10,
        "GroupName": ["Robinson", "Shop", "Robinson", "Online", "Shop", "Robinson", "Online", "Shop", "Robinson", "Shop"],
        "Quantity": [50, 30, 40, 20, 25, 60, 15, 35, 70, 45],
        "LineTotal": [5000, 3000, 4000, 2000, 2500, 6000, 1500, 3500, 7000, 4500],
        "WhsCode": ["WH01", "WH02", "WH01", "D1-SL", "WH03", "WH01", "D1-SL", "WH02", "WH01", "WH03"],
        "Master Price": [100.0] * 10,
        "Price Master": [100.0] * 10,
    })


def _onhand_fixture():
    return pd.DataFrame({
        "ItemCode": ["ITEM1", "ITEM2", "ITEM3", "ITEM1", "ITEM2"],
        "OnHand": [200, 100, 50, 150, 80],
        "WhsCode": ["WH01", "WH02", "D1-SL", "WH03", "WH03"],
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["ITEM1", "ITEM2", "ITEM3"],
        "GroupName": ["BrandA", "BrandB", "BrandC"],
        "ItemName": ["Item One", "Item Two", "Item Three"],
        "Price": [100.0, 100.0, 100.0],
    })


def _whs_fixture():
    return pd.DataFrame({
        "WhsCode": ["WH01", "WH02", "WH03", "D1-SL"],
        "WhsName": ["Main Warehouse", "Shop Store A", "Shop Store B", "Online Shopee+Lazada"],
    })


# ---------------------------------------------------------------------------
# Channel List Tests
# ---------------------------------------------------------------------------

class TestChannelList(unittest.TestCase):

    def test_returns_all_channels(self):
        """Should return all 3 channels in fixture data."""
        result = cha.compute_channel_list(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertIn("channels", result)
        channels = {c["channel"] for c in result["channels"]}
        self.assertEqual(channels, {"Robinson", "Shop", "Online"})

    def test_channel_revenue_sums_to_total(self):
        """Sum of channel revenues should equal total revenue."""
        result = cha.compute_channel_list(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        ch_sum = sum(c["revenue"] for c in result["channels"])
        self.assertAlmostEqual(ch_sum, result["total_revenue"], places=1)

    def test_location_count_per_channel(self):
        """Robinson has WH01, Shop has WH02+WH03, Online has D1-SL."""
        result = cha.compute_channel_list(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        ch_map = {c["channel"]: c for c in result["channels"]}
        self.assertEqual(ch_map["Robinson"]["location_count"], 1)
        self.assertEqual(ch_map["Shop"]["location_count"], 2)
        self.assertEqual(ch_map["Online"]["location_count"], 1)

    def test_year_list_filters(self):
        """year_list=[2025] should return only 2025 data."""
        result_all = cha.compute_channel_list(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        result_2025 = cha.compute_channel_list(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
            year_list=[2025],
        )
        # 2025 has fewer channels (only Robinson and Shop)
        self.assertLessEqual(len(result_2025["channels"]), len(result_all["channels"]))
        # 2025 revenue should be less than all-time
        self.assertLess(result_2025["total_revenue"], result_all["total_revenue"])

    def test_has_description(self):
        """Each channel should have a description."""
        result = cha.compute_channel_list(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        for ch in result["channels"]:
            self.assertIn("description", ch)
            self.assertIsInstance(ch["description"], str)
            self.assertGreater(len(ch["description"]), 0)

    def test_top_location_populated(self):
        """Each channel should have a top_location_name."""
        result = cha.compute_channel_list(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        for ch in result["channels"]:
            self.assertIn("top_location_name", ch)
            self.assertIsInstance(ch["top_location_name"], str)

    def test_empty_data(self):
        """Empty sales should return empty result."""
        empty_sale = pd.DataFrame(columns=_sale_fixture().columns)
        result = cha.compute_channel_list(
            empty_sale, _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertEqual(len(result["channels"]), 0)


# ---------------------------------------------------------------------------
# Channel Detail Tests
# ---------------------------------------------------------------------------

class TestChannelDetail(unittest.TestCase):

    def test_returns_locations_for_channel(self):
        """Robinson should return location WH01."""
        result = cha.compute_channel_detail(
            "Robinson", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertEqual(result["channel"], "Robinson")
        self.assertGreater(len(result["locations"]), 0)
        whs_codes = [l["whs_code"] for l in result["locations"]]
        self.assertIn("WH01", whs_codes)

    def test_shop_has_multiple_locations(self):
        """Shop channel should have WH02 and WH03."""
        result = cha.compute_channel_detail(
            "Shop", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertEqual(result["location_count"], 2)
        whs_codes = {l["whs_code"] for l in result["locations"]}
        self.assertEqual(whs_codes, {"WH02", "WH03"})

    def test_has_brands(self):
        """Should return top brands in this channel."""
        result = cha.compute_channel_detail(
            "Robinson", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertGreater(len(result["brands"]), 0)
        for b in result["brands"]:
            self.assertIn("brand", b)
            self.assertIn("revenue", b)

    def test_has_monthly_trend(self):
        """Should return monthly revenue trend."""
        result = cha.compute_channel_detail(
            "Robinson", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertGreater(len(result["monthly_trend"]), 0)
        for m in result["monthly_trend"]:
            self.assertIn("period", m)
            self.assertIn("revenue", m)

    def test_year_list_filters(self):
        """year_list=[2024] should exclude 2025 data."""
        result_all = cha.compute_channel_detail(
            "Robinson", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        result_2024 = cha.compute_channel_detail(
            "Robinson", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
            year_list=[2024],
        )
        self.assertLess(result_2024["total_revenue"], result_all["total_revenue"])

    def test_nonexistent_channel(self):
        """A channel that doesn't exist should return empty locations."""
        result = cha.compute_channel_detail(
            "FAKE_CHANNEL", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertEqual(len(result["locations"]), 0)
        self.assertEqual(result["total_revenue"], 0)

    def test_location_has_onhand(self):
        """Locations should include on-hand data from snapshot."""
        result = cha.compute_channel_detail(
            "Shop", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        # WH02 has on-hand
        wh02 = next((l for l in result["locations"] if l["whs_code"] == "WH02"), None)
        self.assertIsNotNone(wh02)
        self.assertGreater(wh02["onhand_qty"], 0)

    def test_revenue_per_inventory(self):
        """Locations with on-hand should have revenue_per_inv calculated."""
        result = cha.compute_channel_detail(
            "Shop", _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        for loc in result["locations"]:
            if loc["onhand_thb"] > 0:
                self.assertIsNotNone(loc["revenue_per_inv"])
                self.assertGreater(loc["revenue_per_inv"], 0)


# ---------------------------------------------------------------------------
# Channel-Location Mapping Tests
# ---------------------------------------------------------------------------

class TestChannelLocationMapping(unittest.TestCase):

    def test_returns_all_channels(self):
        """Mapping should include all channels."""
        result = cha.compute_channel_location_mapping(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertIn("mapping", result)
        self.assertIn("Robinson", result["mapping"])
        self.assertIn("Shop", result["mapping"])
        self.assertIn("Online", result["mapping"])

    def test_location_count_matches(self):
        """Each channel's location count should match unique WhsCodes."""
        result = cha.compute_channel_location_mapping(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        self.assertEqual(result["mapping"]["Robinson"]["location_count"], 1)
        self.assertEqual(result["mapping"]["Shop"]["location_count"], 2)
        self.assertEqual(result["mapping"]["Online"]["location_count"], 1)

    def test_locations_sorted_by_revenue(self):
        """Locations within each channel should be sorted by revenue descending."""
        result = cha.compute_channel_location_mapping(
            _sale_fixture(), _onhand_fixture(), _master_fixture(), _whs_fixture(),
        )
        for ch_name, ch_data in result["mapping"].items():
            revenues = [l["revenue"] for l in ch_data["locations"]]
            self.assertEqual(revenues, sorted(revenues, reverse=True),
                           f"Locations in {ch_name} not sorted by revenue")


if __name__ == "__main__":
    unittest.main()
