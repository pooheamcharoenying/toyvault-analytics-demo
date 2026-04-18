"""
Iteration 13: EX-11 Data Trust Strip + Quality Polish.

Tests ensure:
1. Trust strip (line counts) works correctly
2. Global DF structure is valid
3. All functions handle the full data pipeline without error
4. No silent data loss in any module
5. Consistent type handling across modules
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

from app.utils.executive_helpers import global_df_line_counts
from app.utils.nichi_stock import (
    prepare_sales_and_onhand_data,
    generate_sales_onhand_by_channel,
    generate_sales_onhand_by_brand,
    generate_sales_onhand_by_brand_channel,
)
from app.utils.inventory_engine import (
    compute_historical_onhand,
    compute_historical_onhand_org,
)
from app.utils.product_sale_onhand import (
    generate_product_sale_vs_onhand,
    generate_product_sale_vs_onhand_locations,
)


class TestTrustStrip(unittest.TestCase):
    """Tests for EX-11: data trust strip line counts."""

    def test_line_counts_with_data(self):
        """Should return correct row counts for loaded DataFrames."""
        mock_global = {
            "sale": fixtures._medium_sale(),
            "onhand": fixtures._medium_onhand(),
            "master": fixtures._medium_master(),
            "grpo_detail": fixtures._medium_grpo(),
            "whs_code": fixtures._medium_whs_code(),
        }
        result = global_df_line_counts(mock_global)
        self.assertIsInstance(result, dict)
        self.assertIsInstance(result["sale"], int)
        self.assertGreater(result["sale"], 0)
        self.assertIsInstance(result["onhand"], int)
        self.assertGreater(result["onhand"], 0)
        self.assertIsInstance(result["master"], int)
        self.assertGreater(result["master"], 0)

    def test_line_counts_with_none(self):
        """Should return None for missing DataFrames."""
        mock_global = {
            "sale": None,
            "onhand": None,
            "master": None,
            "grpo_detail": None,
            "whs_code": None,
        }
        result = global_df_line_counts(mock_global)
        self.assertIsNone(result["sale"])
        self.assertIsNone(result["onhand"])

    def test_line_counts_with_empty_dict(self):
        """Should handle empty dict gracefully."""
        result = global_df_line_counts({})
        self.assertIsNone(result["sale"])


class TestGlobalDFStructure(unittest.TestCase):
    """Tests that GLOBAL_DF has all required keys."""

    def test_required_keys_exist(self):
        """GLOBAL_DF should have all required keys defined."""
        from app.utils.helper_functions import GLOBAL_DF
        required_keys = ["sale", "onhand", "master", "grpo_detail", "whs_code",
                         "tr_in", "tr_out", "filedate", "filename"]
        for key in required_keys:
            self.assertIn(key, GLOBAL_DF, f"Missing GLOBAL_DF key: {key}")


class TestEndToEndPipeline(unittest.TestCase):
    """Run the full data pipeline to check no silent errors or data loss."""

    def test_full_channel_pipeline(self):
        """Channel report: raw → prepare → generate → split dict."""
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        split = result.to_dict(orient='split')
        self.assertGreater(len(split['data']), 1)  # data rows + total

    def test_full_brand_pipeline(self):
        """Brand report: raw → prepare → generate with engine → split dict."""
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand(
            df_sale, df_onhand,
            df_raw_onhand=onhand,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            file_date=date(2025, 3, 15),
            df_item_master=master,
        )
        split = result.to_dict(orient='split')
        self.assertGreater(len(split['data']), 1)

    def test_full_brand_channel_pipeline(self):
        """Brand-channel report for each known brand."""
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        brands = ["ToyWorld", "FunPlay", "KidZone"]
        for brand in brands:
            result = generate_sales_onhand_by_brand_channel(
                df_sale, df_onhand, brand_name=brand,
                period_type="monthly", year_list=[2024, 2025]
            )
            if not result.empty:
                split = result.to_dict(orient='split')
                self.assertGreater(len(split['columns']), 0,
                    f"Brand-channel for {brand} should have columns")

    def test_full_pso_pipeline(self):
        """Product Sale Vs. OnHand: raw → generate → split dict."""
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        brands = ["ToyWorld", "FunPlay"]
        for brand in brands:
            result = generate_product_sale_vs_onhand(
                df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
                df_grpo_detail=fixtures._medium_grpo(),
                df_tr_in=fixtures._medium_tr_in(),
                df_tr_out=fixtures._medium_tr_out(),
                brand_name=brand, file_date=date(2025, 3, 15),
            )
            if not result.empty:
                split = result.to_dict(orient='split')
                self.assertGreater(len(split['data']), 0,
                    f"PSO for {brand} should have data")

    def test_full_psol_pipeline(self):
        """Product Sale Vs. OnHand by Locations: raw → generate → split dict."""
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        result = generate_product_sale_vs_onhand_locations(
            df_raw_sale=sale, df_raw_onhand=onhand, df_item_master=master,
            df_grpo_detail=fixtures._medium_grpo(),
            df_tr_in=fixtures._medium_tr_in(),
            df_tr_out=fixtures._medium_tr_out(),
            df_whs_code=fixtures._medium_whs_code(),
            brand_name="ToyWorld", file_date=date(2025, 3, 15),
        )
        if not result.empty:
            split = result.to_dict(orient='split')
            self.assertGreater(len(split['data']), 0)


class TestTypeConsistency(unittest.TestCase):
    """All numeric values in outputs should be proper numeric types."""

    def test_channel_numeric_types(self):
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)
        for col in result.columns:
            # All columns should be numeric
            for val in result[col]:
                if pd.notna(val):
                    self.assertTrue(
                        isinstance(val, (int, float, np.integer, np.floating)),
                        f"Non-numeric value in {col}: {type(val)} = {val}"
                    )

    def test_brand_numeric_types(self):
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)
        for col in result.columns:
            for val in result[col]:
                if pd.notna(val):
                    self.assertTrue(
                        isinstance(val, (int, float, np.integer, np.floating)),
                        f"Non-numeric value in {col}: {type(val)} = {val}"
                    )


class TestNoDataLoss(unittest.TestCase):
    """Verify no items silently disappear during processing."""

    def test_all_brands_in_master_appear_in_brand_matrix(self):
        """Brands with sales should all appear in the brand matrix."""
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_brand(df_sale, df_onhand)

        # Get brands that have sales
        sale_brands = set(df_sale['Brand'].dropna().unique())
        result_brands = set(result.index) - {"Total"}

        for brand in sale_brands:
            if brand != "Unknown":
                self.assertIn(brand, result_brands,
                    f"Brand {brand} has sales but is missing from brand matrix")

    def test_all_channels_in_sale_appear_in_channel_matrix(self):
        """Channels with sales should all appear in the channel matrix."""
        sale, onhand, master = fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(sale, onhand, master)
        result = generate_sales_onhand_by_channel(df_sale, df_onhand)

        sale_channels = set(df_sale['GroupName'].dropna().unique())
        result_channels = set(result.index) - {"Total"}

        for ch in sale_channels:
            self.assertIn(ch, result_channels,
                f"Channel {ch} has sales but is missing from channel matrix")


if __name__ == "__main__":
    unittest.main()
