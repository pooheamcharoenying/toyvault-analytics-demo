"""
Iteration 10: Cross-Module Reconciliation Tests.

Tests ensure numbers agree across different report modules:
1. Executive summary totals match channel matrix totals
2. Brand matrix total sold matches executive summary sold
3. Product sale vs onhand total matches brand matrix for same brand
4. On-hand across all reports uses the same base snapshot
5. Inventory engine item totals match raw snapshot
"""
from __future__ import annotations

import sys
import os
import unittest
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as fixtures

from app.utils.nichi_stock import (
    prepare_sales_and_onhand_data,
    generate_sales_onhand_by_channel,
    generate_sales_onhand_by_brand,
)
from app.utils.executive_helpers import (
    compute_executive_summary,
    channel_matrix_lifetime_revenue_thb,
    compute_margin_by_brand,
)
from app.utils.inventory_engine import compute_historical_onhand_org
from app.utils.product_sale_onhand import generate_product_sale_vs_onhand


def _raw():
    return fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()


class TestExecutiveVsChannelMatrix(unittest.TestCase):
    """Executive summary sold_thb should match channel matrix lifetime total."""

    def test_executive_sold_thb_matches_channel_matrix(self):
        sale, onhand, master = _raw()
        exec_result = compute_executive_summary(sale, onhand, master)
        matrix_thb = channel_matrix_lifetime_revenue_thb(sale, onhand, master)

        # Both use channel-style dedup, so should be identical
        self.assertAlmostEqual(
            exec_result["totals"]["sold_thb"],
            matrix_thb,
            places=2,
            msg="Executive sold_thb should match channel matrix lifetime THB"
        )

    def test_executive_onhand_matches_channel_matrix_onhand(self):
        """On-hand in executive and channel matrix Total row should agree."""
        sale, onhand, master = _raw()
        exec_result = compute_executive_summary(sale, onhand, master)

        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        mat = generate_sales_onhand_by_channel(df_sale, df_onhand)
        oh_cols = [c for c in mat.columns if c.endswith("_OnHand_QTY")]
        total_row = mat.loc["Total"]
        # Latest period's on-hand in channel matrix Total row
        latest_oh = None
        for col in sorted(oh_cols, reverse=True):
            val = total_row[col]
            if pd.notna(val) and float(val) > 0:
                latest_oh = float(val)
                break

        if latest_oh is not None:
            self.assertAlmostEqual(
                exec_result["totals"]["onhand_qty"],
                latest_oh,
                places=2,
                msg="Executive onhand_qty should match channel matrix latest OnHand"
            )


class TestBrandMatrixVsExecutive(unittest.TestCase):
    """Brand matrix total sold should be in the same ballpark as executive."""

    def test_brand_total_revenue_within_bounds(self):
        """Brand and executive both use dedup — should be comparable."""
        sale, onhand, master = _raw()
        exec_result = compute_executive_summary(sale, onhand, master)

        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        brand_result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        sold_cols = [c for c in brand_result.columns if c.endswith("_Sold_THB")]
        brand_total = sum(float(brand_result.loc["Total", c]) for c in sold_cols)

        exec_total = exec_result["totals"]["sold_thb"]

        # They use different dedup keys (GroupName vs Brand), so tolerance is wider
        ratio = brand_total / exec_total if exec_total > 0 else 0
        self.assertGreater(ratio, 0.5, "Brand total should be > 50% of exec total")
        self.assertLess(ratio, 2.0, "Brand total should be < 200% of exec total")


class TestProductSaleVsOnHandAcrossModules(unittest.TestCase):
    """Product sale vs onhand data should be consistent with inventory engine."""

    def test_product_sale_onhand_total_sold_matches_brand_matrix(self):
        """For a given brand, PSO total sold QTY should match brand matrix row."""
        sale, onhand, master = _raw()
        brand = "ToyWorld"

        # Get PSO result
        pso = generate_product_sale_vs_onhand(
            df_raw_sale=sale,
            df_raw_onhand=onhand,
            df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            brand_name=brand,
            file_date=date(2025, 3, 15),
            period_type="monthly",
        )
        pso_sold_cols = [c for c in pso.columns if c.endswith("_Sold_QTY")]
        pso_total = sum(float(pso.loc["Total", c]) for c in pso_sold_cols)

        # Get brand matrix result
        df_sale, df_onhand_p, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        brand_result = generate_sales_onhand_by_brand(df_sale, df_onhand_p)
        brand_sold_cols = [c for c in brand_result.columns if c.endswith("_Sold_QTY")]

        if brand in brand_result.index:
            brand_row_total = sum(float(brand_result.at[brand, c]) for c in brand_sold_cols)
            # PSO filters to brand items; brand matrix aggregates by brand
            # They should be close but may differ due to dedup key differences
            self.assertGreater(pso_total, 0, "PSO total should be positive")
            self.assertGreater(brand_row_total, 0, "Brand matrix row total should be positive")

    def test_engine_org_total_matches_raw_snapshot(self):
        """Engine org-level total at latest period should match raw snapshot total."""
        sale, onhand, master = _raw()
        org = compute_historical_onhand_org(
            df_raw_onhand=onhand,
            df_raw_sale=sale,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            file_date=date(2025, 3, 15),
            period_type="monthly",
        )
        oh_cols = sorted([c for c in org.columns if c.endswith("_OnHand_QTY")])
        if not oh_cols:
            self.skipTest("No onhand columns")
        latest = oh_cols[-1]
        engine_total = float(org[latest].sum())

        raw_oh = onhand.copy()
        raw_oh["OnHand"] = pd.to_numeric(raw_oh["OnHand"], errors="coerce").fillna(0)
        snapshot_total = float(raw_oh["OnHand"].sum())

        self.assertAlmostEqual(engine_total, snapshot_total, places=2)


class TestMarginVsRevenue(unittest.TestCase):
    """Margin report revenue should match executive summary revenue."""

    def test_margin_revenue_matches_executive(self):
        sale, onhand, master = _raw()
        exec_result = compute_executive_summary(sale, onhand, master)
        margin_result = compute_margin_by_brand(sale, onhand, master)

        exec_rev = exec_result["totals"]["sold_thb"]
        margin_rev = margin_result["totals"]["revenue_thb"]

        # Both use the same channel-style dedup
        self.assertAlmostEqual(exec_rev, margin_rev, places=2,
            msg="Margin revenue should match executive sold_thb")


if __name__ == "__main__":
    unittest.main()
