"""Tests for product analytics: ABC classification and product-channel fit."""
import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import product_analytics as pa


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _sale_fixture():
    """Sales across 3 items and 3 channels, with clear revenue ranking."""
    dates = (
        ["2024-01-15"] * 6
        + ["2024-02-01"] * 6
        + ["2024-03-10"] * 3
    )
    return pd.DataFrame({
        "DocDate": pd.to_datetime(dates),
        "DocEntry": list(range(1, 16)),
        "ItemCode": [
            "TOP1", "TOP1", "MID1", "MID1", "LOW1", "LOW1",
            "TOP1", "TOP1", "MID1", "MID1", "LOW1", "LOW1",
            "TOP1", "TOP1", "MID1",
        ],
        "ItemName": [
            "Top Item", "Top Item", "Mid Item", "Mid Item", "Low Item", "Low Item",
            "Top Item", "Top Item", "Mid Item", "Mid Item", "Low Item", "Low Item",
            "Top Item", "Top Item", "Mid Item",
        ],
        "Brand": [np.nan] * 15,
        "Price": [100.0] * 15,
        "GroupName": [
            "Robinson", "Online", "Robinson", "Wholesale", "Online", "Wholesale",
            "Robinson", "Online", "Robinson", "Wholesale", "Online", "Wholesale",
            "Robinson", "Online", "Robinson",
        ],
        "Quantity": [
            100, 80, 30, 20, 5, 3,
            100, 80, 30, 20, 5, 3,
            50, 40, 15,
        ],
        "LineTotal": [
            10000, 8000, 3000, 2000, 500, 300,
            10000, 8000, 3000, 2000, 500, 300,
            5000, 4000, 1500,
        ],
        "WhsCode": ["WH01"] * 15,
        "Master Price": [100.0] * 15,
        "Price Master": [100.0] * 15,
    })


def _onhand_fixture():
    return pd.DataFrame({
        "ItemCode": ["TOP1", "MID1", "LOW1"],
        "OnHand": [200, 100, 50],
        "WhsCode": ["WH01", "WH01", "WH01"],
    })


def _master_fixture():
    return pd.DataFrame({
        "ItemCode": ["TOP1", "MID1", "LOW1"],
        "GroupName": ["BrandA", "BrandB", "BrandC"],
        "ItemName": ["Top Item", "Mid Item", "Low Item"],
        "Price": [100.0, 100.0, 100.0],
    })


# ---------------------------------------------------------------------------
# ABC Classification Tests
# ---------------------------------------------------------------------------

class TestABCClassification(unittest.TestCase):

    def test_basic_classification(self):
        """Items should be classified A/B/C based on cumulative revenue."""
        result = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="item",
        )
        self.assertIn("rows", result)
        self.assertIn("summary", result)
        self.assertGreater(len(result["rows"]), 0)

        # TOP1 should be rank 1 (highest revenue)
        rows = result["rows"]
        self.assertEqual(rows[0]["item_code"], "TOP1")
        self.assertEqual(rows[0]["rank"], 1)

        # Check classes exist
        classes = {r["abc_class"] for r in rows}
        self.assertTrue(len(classes) >= 1)

        # Summary should have A class
        self.assertIn("A", result["summary"])

    def test_classification_revenue_ordering(self):
        """Rows should be ordered by revenue descending."""
        result = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="item",
        )
        revenues = [r["revenue_thb"] for r in result["rows"]]
        self.assertEqual(revenues, sorted(revenues, reverse=True))

    def test_cumulative_pct_reaches_100(self):
        """Cumulative % should reach ~100 for last item."""
        result = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="item",
        )
        last_row = result["rows"][-1]
        self.assertAlmostEqual(last_row["cumulative_pct"], 100.0, places=0)

    def test_brand_dimension(self):
        """Brand dimension should aggregate by brand."""
        result = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="brand",
        )
        self.assertGreater(len(result["rows"]), 0)
        # Each row should have 'brand' and 'sku_count'
        for row in result["rows"]:
            self.assertIn("brand", row)
            self.assertIn("sku_count", row)

    def test_year_filter(self):
        """Year filter should restrict data."""
        result_all = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
        )
        result_2024 = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            year=2024,
        )
        result_2020 = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            year=2020,
        )
        # 2024 should have data, 2020 should be empty
        self.assertGreater(len(result_2024["rows"]), 0)
        self.assertEqual(len(result_2020["rows"]), 0)

    def test_summary_revenue_equals_total(self):
        """Sum of class revenues should equal total revenue."""
        result = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="item",
        )
        summary = result["summary"]
        sum_rev = sum(v["revenue_thb"] for v in summary.values())
        self.assertAlmostEqual(sum_rev, result["total_revenue_thb"], places=1)

    def test_custom_thresholds(self):
        """Custom thresholds should shift classification boundaries."""
        result_strict = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            a_threshold=50.0, b_threshold=90.0,
        )
        result_loose = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            a_threshold=99.0, b_threshold=99.9,
        )
        # With loose thresholds, more items should be A
        a_strict = sum(1 for r in result_strict["rows"] if r["abc_class"] == "A")
        a_loose = sum(1 for r in result_loose["rows"] if r["abc_class"] == "A")
        self.assertGreaterEqual(a_loose, a_strict)

    def test_onhand_qty_present(self):
        """Each row should have on-hand quantity."""
        result = pa.compute_abc_classification(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="item",
        )
        for row in result["rows"]:
            self.assertIn("onhand_qty", row)

    def test_empty_data(self):
        """Empty sales should return empty result."""
        empty_sale = pd.DataFrame(columns=_sale_fixture().columns)
        result = pa.compute_abc_classification(
            empty_sale, _onhand_fixture(), _master_fixture(),
        )
        self.assertEqual(len(result["rows"]), 0)


# ---------------------------------------------------------------------------
# Product-Channel Fit Tests
# ---------------------------------------------------------------------------

class TestProductChannelFit(unittest.TestCase):

    def test_basic_matrix(self):
        """Should return a matrix with products and channel breakdowns."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="brand",
        )
        self.assertIn("matrix", result)
        self.assertIn("channels", result)
        self.assertIn("top_per_channel", result)
        self.assertIn("summary", result)
        self.assertGreater(len(result["matrix"]), 0)
        self.assertGreater(len(result["channels"]), 0)

    def test_channels_list(self):
        """Channels list should match actual channels in data."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
        )
        expected_channels = {"Robinson", "Online", "Wholesale"}
        self.assertEqual(set(result["channels"]), expected_channels)

    def test_matrix_row_structure(self):
        """Each matrix row should have product, total_revenue, channels dict."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="brand",
        )
        for row in result["matrix"]:
            self.assertIn("product", row)
            self.assertIn("total_revenue", row)
            self.assertIn("channels", row)
            self.assertIn("channel_count", row)
            self.assertIsInstance(row["channels"], dict)

    def test_channel_revenue_sums_to_total(self):
        """Per-channel revenues should sum to total_revenue for each product."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="brand",
        )
        for row in result["matrix"]:
            ch_sum = sum(v["revenue"] for v in row["channels"].values())
            self.assertAlmostEqual(ch_sum, row["total_revenue"], places=1)

    def test_item_dimension(self):
        """Item dimension should show individual items."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="item",
        )
        self.assertGreater(len(result["matrix"]), 0)
        # Items should have description and brand
        for row in result["matrix"]:
            self.assertIn("description", row)
            self.assertIn("brand", row)

    def test_top_per_channel(self):
        """top_per_channel should have entries for each channel."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
        )
        for ch in result["channels"]:
            self.assertIn(ch, result["top_per_channel"])
            self.assertGreater(len(result["top_per_channel"][ch]), 0)

    def test_channel_summary(self):
        """Channel summary should have revenue and product count."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
        )
        for ch, data in result["summary"].items():
            self.assertIn("revenue", data)
            self.assertIn("revenue_pct", data)
            self.assertIn("product_count", data)

    def test_year_filter(self):
        """Year filter should restrict data."""
        result_2024 = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            year=2024,
        )
        result_2020 = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            year=2020,
        )
        self.assertGreater(len(result_2024["matrix"]), 0)
        self.assertEqual(len(result_2020["matrix"]), 0)

    def test_top_n_limit(self):
        """top_n should limit the number of products in matrix."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="item", top_n=2,
        )
        self.assertLessEqual(len(result["matrix"]), 2)

    def test_empty_data(self):
        """Empty sales should return empty result."""
        empty_sale = pd.DataFrame(columns=_sale_fixture().columns)
        result = pa.compute_product_channel_fit(
            empty_sale, _onhand_fixture(), _master_fixture(),
        )
        self.assertEqual(len(result["matrix"]), 0)

    def test_channel_count_accuracy(self):
        """channel_count should reflect how many channels have revenue > 0."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            dimension="brand",
        )
        for row in result["matrix"]:
            expected = sum(1 for v in row["channels"].values() if v["revenue"] > 0)
            self.assertEqual(row["channel_count"], expected)


class TestProductChannelFitYearList(unittest.TestCase):
    """Tests for OBJ-87: year_list multi-year filtering in product-channel fit."""

    def _multi_year_sale(self):
        """Sales spanning 2023 and 2024 across 3 channels."""
        return pd.DataFrame({
            "DocDate": pd.to_datetime([
                "2023-06-01", "2023-06-02", "2023-06-03",
                "2024-01-15", "2024-02-01", "2024-03-10",
            ]),
            "DocEntry": list(range(1, 7)),
            "ItemCode": ["TOP1", "MID1", "LOW1", "TOP1", "MID1", "LOW1"],
            "ItemName": ["Top Item", "Mid Item", "Low Item", "Top Item", "Mid Item", "Low Item"],
            "Brand": [np.nan] * 6,
            "Price": [100.0] * 6,
            "GroupName": ["Robinson", "Online", "Wholesale", "Robinson", "Online", "Wholesale"],
            "Quantity": [100, 30, 5, 80, 20, 3],
            "LineTotal": [10000, 3000, 500, 8000, 2000, 300],
            "WhsCode": ["WH01"] * 6,
            "Master Price": [100.0] * 6,
            "Price Master": [100.0] * 6,
        })

    def test_year_list_filters_correctly(self):
        """year_list=[2024] should return only 2024 data."""
        result = pa.compute_product_channel_fit(
            self._multi_year_sale(), _onhand_fixture(), _master_fixture(),
            year_list=[2024],
        )
        self.assertGreater(len(result["matrix"]), 0)
        self.assertEqual(result["year_list"], [2024])
        # Revenue should be less than all-years total
        result_all = pa.compute_product_channel_fit(
            self._multi_year_sale(), _onhand_fixture(), _master_fixture(),
        )
        total_2024 = sum(r["total_revenue"] for r in result["matrix"])
        total_all = sum(r["total_revenue"] for r in result_all["matrix"])
        self.assertLess(total_2024, total_all)

    def test_year_list_multi_year(self):
        """year_list=[2023, 2024] should include both years."""
        result = pa.compute_product_channel_fit(
            self._multi_year_sale(), _onhand_fixture(), _master_fixture(),
            year_list=[2023, 2024],
        )
        self.assertGreater(len(result["matrix"]), 0)
        self.assertEqual(set(result["year_list"]), {2023, 2024})
        # Revenue should include both years
        total_both = sum(r["total_revenue"] for r in result["matrix"])
        self.assertGreater(total_both, 10000)  # At least TOP1's combined revenue

    def test_year_list_takes_precedence_over_year(self):
        """When both year and year_list are provided, year_list wins."""
        result = pa.compute_product_channel_fit(
            self._multi_year_sale(), _onhand_fixture(), _master_fixture(),
            year=2023, year_list=[2024],
        )
        # Should use year_list=[2024], not year=2023
        self.assertEqual(result["year_list"], [2024])

    def test_year_list_empty_result(self):
        """year_list for a year with no data should return empty."""
        result = pa.compute_product_channel_fit(
            self._multi_year_sale(), _onhand_fixture(), _master_fixture(),
            year_list=[2020],
        )
        self.assertEqual(len(result["matrix"]), 0)

    def test_all_channels_returned(self):
        """All channels present in data should appear in the response."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
        )
        # Fixture has Robinson, Online, Wholesale
        self.assertGreaterEqual(len(result["channels"]), 3)
        self.assertIn("Robinson", result["channels"])
        self.assertIn("Online", result["channels"])
        self.assertIn("Wholesale", result["channels"])
        # All channels should appear in summary
        for ch in result["channels"]:
            self.assertIn(ch, result["summary"])

    def test_response_has_year_list_key(self):
        """Response should use year_list key instead of year."""
        result = pa.compute_product_channel_fit(
            _sale_fixture(), _onhand_fixture(), _master_fixture(),
            year_list=[2024],
        )
        self.assertIn("year_list", result)


class TestIlocSafety(unittest.TestCase):
    """Regression tests for OBJ-45: empty DataFrame .iloc[0] guards."""

    def test_product_channel_fit_single_item_no_crash(self):
        """Single item across channels should not crash on .iloc access."""
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-01-15"]),
            "DocEntry": [1],
            "ItemCode": ["ITEM1"],
            "ItemName": ["Test Item"],
            "Brand": [np.nan],
            "Price": [50.0],
            "GroupName": ["Robinson"],
            "Quantity": [10],
            "LineTotal": [500.0],
            "WhsCode": ["WH01"],
            "Master Price": [50.0],
            "Price Master": [50.0],
        })
        onhand = pd.DataFrame({
            "ItemCode": ["ITEM1"],
            "OnHand": [5],
            "WhsCode": ["WH01"],
        })
        master = pd.DataFrame({
            "ItemCode": ["ITEM1"],
            "GroupName": ["TestBrand"],
            "ItemName": ["Test Item"],
            "Price": [50.0],
        })
        result = pa.compute_product_channel_fit(sale, onhand, master, dimension="item")
        self.assertEqual(len(result["matrix"]), 1)
        self.assertEqual(result["matrix"][0]["product"], "ITEM1")
        self.assertGreater(result["matrix"][0]["total_revenue"], 0)

    def test_abc_empty_sales_no_crash(self):
        """ABC classification with completely empty sales must not crash."""
        empty_sale = pd.DataFrame(columns=_sale_fixture().columns)
        result = pa.compute_abc_classification(
            empty_sale, _onhand_fixture(), _master_fixture(),
        )
        self.assertEqual(len(result["rows"]), 0)

    def test_product_channel_fit_empty_sales_no_crash(self):
        """Product-channel fit with empty sales must not crash."""
        empty_sale = pd.DataFrame(columns=_sale_fixture().columns)
        result = pa.compute_product_channel_fit(
            empty_sale, _onhand_fixture(), _master_fixture(),
        )
        self.assertEqual(len(result["matrix"]), 0)


if __name__ == "__main__":
    unittest.main()
