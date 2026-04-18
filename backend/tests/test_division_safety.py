"""
Regression tests for division-by-zero safety guards across backend utilities.

Ensures that functions producing ratios, percentages, or averages
never crash or produce unclean NaN/Inf when denominators are zero.
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

from app.utils.nichi_stock import prepare_sales_and_onhand_data


class TestBrandProductProfitLossZeroQty(unittest.TestCase):
    """nichi_stock.generate_brand_product_profit_loss — zero GRPO quantity guard."""

    def _prep_data(self):
        """Prepare sale/onhand with Brand column via prepare_sales_and_onhand_data."""
        sale = fixtures._medium_sale()
        onhand = fixtures._medium_onhand()
        master = fixtures._medium_master()
        df_sale, df_onhand, _ = prepare_sales_and_onhand_data(
            sale.copy(), onhand.copy(), master.copy()
        )
        return df_sale, df_onhand, master

    def test_zero_quantity_grpo_no_crash(self):
        """If GRPO records have Quantity=0, weighted FOB must not crash."""
        from app.utils.nichi_stock import generate_brand_product_profit_loss

        df_sale, df_onhand, master = self._prep_data()
        brand = "ALL FOR PLAY"
        brand_items = master[master["GroupName"] == brand]["ItemCode"].tolist()

        grpo = pd.DataFrame([
            {
                "DocDate": pd.Timestamp(2024, 6, 1),
                "DocEntry": 9999,
                "ItemCode": brand_items[0] if brand_items else "ITEM-000",
                "ItemName": "Zero qty purchase",
                "Quantity": 0,  # zero quantity — the edge case
                "Price": 10.0,
                "Currency": "USD",
                "Rate": 35.0,
                "LineTotal": 0,
                "WhsCode": "WH01",
                "CardCode": "V001",
                "CardName": "Vendor",
                "ShipDate": pd.Timestamp(2024, 6, 1),
                "TargetType": "", "TrgetEntry": "",
                "BaseType": "", "BaseEntry": "", "BaseRef": "",
                "LineNum": 0,
            }
        ])

        # Should not raise ZeroDivisionError
        result = generate_brand_product_profit_loss(df_sale, df_onhand, grpo, brand)
        self.assertIsInstance(result, pd.DataFrame)

    def test_normal_grpo_produces_valid_fob(self):
        """Normal GRPO data should produce non-NaN FOB values."""
        from app.utils.nichi_stock import generate_brand_product_profit_loss

        df_sale, df_onhand, _ = self._prep_data()
        grpo = fixtures._medium_grpo()
        brand = "ALL FOR PLAY"

        result = generate_brand_product_profit_loss(df_sale, df_onhand, grpo, brand)
        self.assertIsInstance(result, pd.DataFrame)
        if not result.empty and "FOB_Price_THB" in result.columns:
            fob_col = result["FOB_Price_THB"]
            self.assertFalse(fob_col.isna().any(), "FOB_Price_THB contains NaN")
            self.assertFalse(np.isinf(fob_col).any(), "FOB_Price_THB contains Inf")


class TestLocationAnalyticsSafeDiv(unittest.TestCase):
    """location_analytics — all divisions guarded."""

    def test_empty_sales_no_crash(self):
        """Location performance with no sales should not crash."""
        from app.utils.location_analytics import compute_location_performance

        sale = fixtures._medium_sale()
        onhand = fixtures._medium_onhand()
        master = fixtures._medium_master()
        whs = fixtures._medium_whs_code()

        # Empty sale DataFrame (same columns, no rows)
        empty_sale = sale.head(0).copy()

        result = compute_location_performance(
            df_raw_sale=empty_sale,
            df_raw_onhand=onhand,
            df_item_master=master,
            df_whs_code=whs,
            window_days=90,
        )
        self.assertIsInstance(result, dict)
        for loc in result.get("locations", []):
            for key in ["revenue_per_thb_inventory", "sell_through_rate", "dead_stock_pct"]:
                val = loc.get(key, 0)
                if val is not None:
                    self.assertFalse(np.isnan(val), f"{key} is NaN for {loc.get('location')}")
                    self.assertFalse(np.isinf(val), f"{key} is Inf for {loc.get('location')}")


class TestExecutiveHelpersSafeDiv(unittest.TestCase):
    """executive_helpers — MoM/YoY percentage calculations."""

    def test_zero_revenue_period_no_crash(self):
        """Periods with zero revenue should not crash MoM calculation."""
        from app.utils.executive_helpers import compute_executive_summary

        sale = fixtures._medium_sale()
        onhand = fixtures._medium_onhand()
        master = fixtures._medium_master()

        result = compute_executive_summary(
            df_raw_sale=sale,
            df_raw_onhand=onhand,
            df_item_master=master,
        )
        self.assertIsInstance(result, dict)
        comparison = result.get("comparison")
        if comparison is not None:
            mom = comparison.get("revenue_mom_pct")
            if mom is not None:
                self.assertFalse(np.isnan(mom), "MoM pct is NaN")
                self.assertFalse(np.isinf(mom), "MoM pct is Inf")


if __name__ == "__main__":
    unittest.main()
