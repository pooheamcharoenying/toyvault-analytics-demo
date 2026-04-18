"""Integrity tests for analytics preparation and channel on-hand handling."""
import sys
import os
import unittest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401 — ensures mocks are set up

from app.utils import nichi_stock as nstk


def _minimal_sale():
    return pd.DataFrame(
        {
            "DocDate": pd.to_datetime(["2024-01-15", "2024-02-15"]),
            "DocEntry": [1, 2],
            "ItemCode": ["A1", "A1"],
            "ItemName": ["Item", "Item"],
            "Brand": [np.nan, "LineBrand"],
            "Price": [10.0, 10.0],
            "GroupName": ["Ch1", "Ch2"],
            "Quantity": [1, 2],
            "LineTotal": [100.0, 200.0],
            "WhsCode": ["WHFULL01", "WHFULL01"],
            "Master Price": [100.0, 100.0],
            "Price Master": [100.0, 100.0],
        }
    )


def _minimal_onhand():
    return pd.DataFrame(
        {
            "ItemCode": ["A1", "A2"],
            "OnHand": [5, 3],
            "WhsCode": ["WHFULL01", "WHFULL01"],
        }
    )


def _minimal_master():
    return pd.DataFrame(
        {
            "ItemCode": ["A1", "A2"],
            "GroupName": ["MasterBrand", "OtherBrand"],
            "ItemName": ["N1", "N2"],
            "Price": [100.0, 50.0],
        }
    )


class TestPrepareSalesAndOnhand(unittest.TestCase):
    def test_brand_filled_from_master_when_line_brand_missing(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        ds, oh_out, _ = nstk.prepare_sales_and_onhand_data(sale, oh, master)
        self.assertEqual(ds.loc[0, "Brand"], "MasterBrand")
        self.assertEqual(ds.loc[1, "Brand"], "LineBrand")

    def test_does_not_mutate_original_sale_frame(self):
        sale = _minimal_sale()
        before = sale["DocDate"].tolist()
        nstk.prepare_sales_and_onhand_data(sale, _minimal_onhand(), _minimal_master())
        self.assertEqual(sale["DocDate"].tolist(), before)

    def test_requires_item_master(self):
        with self.assertRaises(ValueError):
            nstk.prepare_sales_and_onhand_data(_minimal_sale(), _minimal_onhand(), None)


class TestChannelOnHandIntegrity(unittest.TestCase):
    def test_per_channel_onhand_nan_org_total_in_total_row_only(self):
        sale = _minimal_sale()
        oh = _minimal_onhand()
        master = _minimal_master()
        ds, oh_p, _ = nstk.prepare_sales_and_onhand_data(sale, oh, master)
        out = nstk.generate_sales_onhand_by_channel(ds, oh_p, period_type="monthly")
        self.assertFalse(out.empty)
        oh_cols = [c for c in out.columns if "_OnHand_" in c]
        data_rows = out.iloc[:-1]
        self.assertTrue(data_rows[oh_cols].isna().all().all())
        total = out.iloc[-1]
        latest_oh_qty_cols = [c for c in oh_cols if c.endswith("_OnHand_QTY")]
        self.assertTrue(len(latest_oh_qty_cols) >= 1)
        non_nan_totals = total[latest_oh_qty_cols].dropna()
        self.assertEqual(len(non_nan_totals), 1)
        self.assertAlmostEqual(float(non_nan_totals.iloc[0]), 8.0)


class TestSummarizeLocationWhsCode(unittest.TestCase):
    def test_full_whs_code_merge(self):
        sale = pd.DataFrame(
            {
                "DocDate": pd.to_datetime(["2024-06-01"]),
                "ItemCode": ["A1"],
                "Quantity": [2.0],
                "WhsCode": ["LONGWH99"],
                "Price Master": [10.0],
            }
        )
        oh = pd.DataFrame(
            {"ItemCode": ["A1"], "OnHand": [1.0], "WhsCode": ["LONGWH99"]}
        )
        whs = pd.DataFrame({"WhsCode": ["LONGWH99"], "WhsName": ["Store Nine"]})
        master = pd.DataFrame({"ItemCode": ["A1"], "Price": [10.0]})
        out = nstk.summarize_sales_onhand_by_location(
            "dummy (20240601).xlsx", sale, oh, whs, master
        )
        self.assertIn("Store Nine", out.index)


if __name__ == "__main__":
    unittest.main()
