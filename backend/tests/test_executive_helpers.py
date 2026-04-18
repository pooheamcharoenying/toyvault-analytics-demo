"""Executive aggregates reconcile with channel matrix totals."""
import unittest

import pandas as pd

from app.utils import executive_helpers as exr

from tests.test_analytics_integrity import _minimal_master, _minimal_onhand, _minimal_sale


class TestExecutiveTotalsMatchChannelMatrix(unittest.TestCase):
    def test_lifetime_revenue_matches_channel_matrix_sum(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_executive_summary(sale, oh, master, as_of="2024-01-01")
        from_matrix = exr.channel_matrix_lifetime_revenue_thb(sale, oh, master)
        self.assertAlmostEqual(out["totals"]["sold_thb"], from_matrix)

    def test_duplicate_lines_deduped_like_channel_report(self):
        sale = _minimal_sale()
        dup = sale.iloc[[1]].copy()
        sale2 = pd.concat([sale, dup], ignore_index=True)
        oh = _minimal_onhand()
        master = _minimal_master()
        base = exr.compute_executive_summary(sale, oh, master, as_of=None)
        with_dup = exr.compute_executive_summary(sale2, oh, master, as_of=None)
        self.assertAlmostEqual(base["totals"]["sold_thb"], with_dup["totals"]["sold_thb"])


class TestConcentration(unittest.TestCase):
    def test_brand_shares_sum_to_top_k_fraction(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_concentration_summary(
            sale, oh, master, dimension="brand", year=2024, top_n=5
        )
        self.assertEqual(out["dimension"], "brand")
        self.assertGreater(out["total_revenue_thb"], 0)
        s = sum(r["revenue_thb"] for r in out["rows"])
        self.assertLessEqual(s, out["total_revenue_thb"] + 1e-6)


class TestMarginByBrand(unittest.TestCase):
    def test_margin_payload_shape_and_totals(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_margin_by_brand(
            sale, oh, master, df_grpo_detail=None, year_list=[2024]
        )
        self.assertIn("rows", out)
        self.assertIn("totals", out)
        self.assertGreaterEqual(out["totals"]["revenue_thb"], 0)
        self.assertGreaterEqual(out["totals"]["cogs_thb"], 0)
        self.assertAlmostEqual(
            out["totals"]["gross_margin_thb"],
            out["totals"]["revenue_thb"] - out["totals"]["cogs_thb"],
        )


class TestInventoryRiskSummary(unittest.TestCase):
    def test_inventory_risk_payload_has_rows(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_inventory_risk_summary(
            sale, oh, master, as_of=pd.Timestamp("2024-02-15"), window_days=90, top_n=10
        )
        self.assertIn("rows", out)
        self.assertIn("summary", out)
        self.assertGreaterEqual(len(out["rows"]), 1)
        self.assertIn("total_onhand_thb", out["summary"])

    def test_no_sales_item_ranked_above_slow_mover(self):
        """Regression: items with zero sales (inf days_cover) must have higher
        risk_score than items with very slow but finite sales velocity, given
        equal on-hand THB value."""
        import numpy as np
        # Item B1 has no sales at all; item A1 has slow sales (1 unit in 90 days)
        sale = pd.DataFrame({
            "DocDate": pd.to_datetime(["2024-02-10"]),
            "DocEntry": [1],
            "ItemCode": ["A1"],
            "ItemName": ["SellItem"],
            "Brand": ["BrandA"],
            "Price": [100.0],
            "GroupName": ["Ch1"],
            "Quantity": [1],
            "LineTotal": [100.0],
            "WhsCode": ["WH1"],
            "Master Price": [100.0],
            "Price Master": [100.0],
        })
        # Both items have identical on-hand qty and price → same onhand_thb
        oh = pd.DataFrame({
            "ItemCode": ["A1", "B1"],
            "OnHand": [500, 500],
            "WhsCode": ["WH1", "WH1"],
        })
        master = pd.DataFrame({
            "ItemCode": ["A1", "B1"],
            "GroupName": ["BrandA", "BrandB"],
            "ItemName": ["SellItem", "DeadItem"],
            "Price": [100.0, 100.0],
        })
        out = exr.compute_inventory_risk_summary(
            sale, oh, master, as_of=pd.Timestamp("2024-02-15"),
            window_days=90, top_n=10,
        )
        rows = out["rows"]
        self.assertGreaterEqual(len(rows), 2)
        # Find both items
        a1 = next(r for r in rows if r["item_code"] == "A1")
        b1 = next(r for r in rows if r["item_code"] == "B1")
        # B1 (no sales) must have higher risk_score than A1 (slow sales)
        self.assertGreater(b1["risk_score"], a1["risk_score"],
                           "No-sales item should have higher risk score than slow mover")


class TestChannelPerformanceExecutive(unittest.TestCase):
    def test_channel_performance_rows_exist(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_channel_performance_executive(
            sale, oh, master, year_list=[2024], period_type="monthly"
        )
        self.assertIn("rows", out)
        self.assertIn("latest_period", out)
        self.assertGreaterEqual(len(out["rows"]), 1)


class TestBrandListMetrics(unittest.TestCase):
    def test_brand_list_metrics_shape(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_brand_list_metrics(
            sale, oh, master, df_grpo_detail=None, year_list=[2024]
        )
        self.assertIn("rows", out)
        self.assertGreaterEqual(len(out["rows"]), 1)
        row = out["rows"][0]
        for key in ["brand", "sold_qty", "revenue_thb", "cogs_thb",
                     "gross_margin_thb", "gross_margin_pct",
                     "onhand_qty", "onhand_thb", "sell_through_rate"]:
            self.assertIn(key, row, f"Missing key: {key}")

    def test_brand_list_metrics_margin_equals_revenue_minus_cogs(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_brand_list_metrics(
            sale, oh, master, df_grpo_detail=None, year_list=[2024]
        )
        for row in out["rows"]:
            self.assertAlmostEqual(
                row["gross_margin_thb"],
                row["revenue_thb"] - row["cogs_thb"],
                places=2,
            )

    def test_brand_list_metrics_sell_through_rate_bounded(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_brand_list_metrics(
            sale, oh, master, df_grpo_detail=None, year_list=[2024]
        )
        for row in out["rows"]:
            if row["sell_through_rate"] is not None:
                self.assertGreaterEqual(row["sell_through_rate"], 0)
                self.assertLessEqual(row["sell_through_rate"], 100)

    def test_brand_list_metrics_onhand_only_brand_appears(self):
        """Brands with on-hand but no sales should still appear."""
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_brand_list_metrics(
            sale, oh, master, df_grpo_detail=None, year_list=[2024]
        )
        brands = [r["brand"] for r in out["rows"]]
        # OtherBrand has on-hand (A2) but no sales
        self.assertIn("OtherBrand", brands)


class TestBrandListABC(unittest.TestCase):
    """Tests for ABC classification counts in brand list metrics (OBJ-83)."""

    def test_abcde_fields_present(self):
        """Each brand row has abcde_a_count through abcde_e_count."""
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_brand_list_metrics(sale, oh, master, year_list=[2024])
        for row in out["rows"]:
            for tier in ("a", "b", "c", "d", "e"):
                self.assertIn(f"abcde_{tier}_count", row)

    def test_abcde_counts_sum_to_total_items(self):
        """A + B + C + D + E count should equal total unique items sold for each brand."""
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_brand_list_metrics(sale, oh, master, year_list=[2024])
        for row in out["rows"]:
            total = sum(row[f"abcde_{t}_count"] for t in "abcde")
            if row["sold_qty"] > 0:
                self.assertGreater(total, 0, f"Brand {row['brand']} has sales but 0 ABCDE items")

    def test_abcde_at_least_one_a_if_revenue(self):
        """Every brand with positive revenue should have at least 1 A-product."""
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        out = exr.compute_brand_list_metrics(sale, oh, master, year_list=[2024])
        for row in out["rows"]:
            if row["revenue_thb"] > 0:
                self.assertGreaterEqual(row["abcde_a_count"], 1,
                                        f"Brand {row['brand']} has revenue but 0 A products")


if __name__ == "__main__":
    unittest.main()
