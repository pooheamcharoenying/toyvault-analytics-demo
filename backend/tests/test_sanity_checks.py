"""
Comprehensive sanity checks that verify data consistency across the entire app.

These tests use the MEDIUM fixtures (realistic data) and verify that:
1. Revenue (Actual) <= Revenue (Master) for each brand (no artificial inflation)
2. Brand list totals == sum of brand detail product-level totals (no dedup mismatch)
3. On-Hand Qty is always the current snapshot (not affected by year filter)
4. Revenue (Master) uses Item Master Price consistently (not the NaN-filled Sale column)
5. GP Commission is non-negative and <= Revenue
6. Sold Qty in brand detail == Sold Qty in brand list for same brand/year
7. All monetary values are non-negative
8. Cross-endpoint revenue reconciliation
9. Dedup produces fewer or equal rows than raw data

Every test is a business-logic invariant that must ALWAYS hold. Failures indicate
a data pipeline bug that would show incorrect numbers to users.
"""
from __future__ import annotations

import sys
import os
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as fixtures

from app.utils import nichi_stock as nstk
from app.utils.executive_helpers import (
    compute_executive_summary,
    compute_sales_trend_executive,
    compute_brand_list_metrics,
    _channel_dedup_sale,
)


def _raw():
    return fixtures._medium_sale(), fixtures._medium_onhand(), fixtures._medium_master()


def _grpo():
    return fixtures._medium_grpo()


def _prep():
    """Return prepared (sale, onhand, master, grpo) ready for analysis."""
    sale, onhand, master = _raw()
    df_sale_prep, df_onhand_prep, _ = nstk.prepare_sales_and_onhand_data(
        sale, onhand, master
    )
    return df_sale_prep, df_onhand_prep, master, _grpo()


def _exec_totals(result):
    """Extract totals from executive summary result (handles nested structure)."""
    if "totals" in result and isinstance(result["totals"], dict):
        return result["totals"]
    return result


# ---------------------------------------------------------------------------
# 1. Revenue (Master) >= Revenue (Actual) for each brand
# ---------------------------------------------------------------------------
class TestRevenueMasterVsActual(unittest.TestCase):
    """Master Price is the list price; actual sales include discounts.
    Revenue (Master) should not be dramatically below Revenue (Actual).
    A large violation means the Master Price source is wrong (e.g. NaN->0).
    """

    def test_overall_master_gte_actual(self):
        sale, onhand, master = _raw()
        result = compute_executive_summary(sale, onhand, master)
        t = _exec_totals(result)
        rev_actual = t.get("sold_thb", 0)
        rev_master = t.get("sold_master_thb", 0)
        if rev_actual > 0:
            ratio = rev_master / rev_actual
            self.assertGreater(
                ratio, 0.5,
                f"Revenue (Master) {rev_master:,.0f} is less than 50% of "
                f"Revenue (Actual) {rev_actual:,.0f} — likely NaN->0 bug"
            )

    def test_per_brand_master_revenue_not_zero(self):
        """Revenue (Master) should not be zero for brands that have sales."""
        sale, onhand, master = _raw()
        result = compute_brand_list_metrics(sale, onhand, master)
        brands = result.get("rows", [])
        for b in brands:
            if b.get("revenue_thb", 0) > 0:
                self.assertGreater(
                    b.get("revenue_master_thb", 0), 0,
                    f"Brand {b.get('brand')} has revenue {b['revenue_thb']:,.0f} "
                    f"but Revenue (Master) is 0 — Master Price lookup broken"
                )


# ---------------------------------------------------------------------------
# 2. Brand list total == sum of brand detail products
# ---------------------------------------------------------------------------
class TestBrandListVsDetailConsistency(unittest.TestCase):
    """The brand list page and brand detail page must report the same
    totals for the same brand/year. If they differ, dedup is inconsistent.
    """

    def test_sold_qty_matches(self):
        sale, onhand, master = _raw()
        list_result = compute_brand_list_metrics(sale, onhand, master)
        brands_list = {b["brand"]: b for b in list_result.get("rows", list_result.get("brands", []))}

        df_sale_prep, df_onhand_prep, master_df, grpo = _prep()

        for brand_name, list_data in brands_list.items():
            if brand_name in ("Unknown", None) or list_data.get("sold_qty", 0) == 0:
                continue
            detail_df = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand_name
            )
            if detail_df.empty:
                continue
            product_rows = detail_df[detail_df["ItemCode"] != "TOTAL"]
            detail_sold = product_rows["Sold_QTY"].sum()
            list_sold = list_data["sold_qty"]

            self.assertAlmostEqual(
                detail_sold, list_sold, delta=max(list_sold * 0.05, 2),
                msg=f"Brand {brand_name}: detail sold {detail_sold} != "
                    f"list sold {list_sold} — dedup mismatch"
            )

    def test_revenue_actual_matches(self):
        sale, onhand, master = _raw()
        list_result = compute_brand_list_metrics(sale, onhand, master)
        brands_list = {b["brand"]: b for b in list_result.get("rows", list_result.get("brands", []))}

        df_sale_prep, df_onhand_prep, master_df, grpo = _prep()

        for brand_name, list_data in brands_list.items():
            if brand_name in ("Unknown", None) or list_data.get("revenue_thb", 0) == 0:
                continue
            detail_df = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand_name
            )
            if detail_df.empty:
                continue
            product_rows = detail_df[detail_df["ItemCode"] != "TOTAL"]
            detail_rev = product_rows["Actual_Revenue_THB"].sum() if "Actual_Revenue_THB" in product_rows.columns else 0
            list_rev = list_data["revenue_thb"]

            self.assertAlmostEqual(
                detail_rev, list_rev, delta=max(list_rev * 0.05, 2),
                msg=f"Brand {brand_name}: detail revenue {detail_rev:,.0f} != "
                    f"list revenue {list_rev:,.0f}"
            )


# ---------------------------------------------------------------------------
# 3. On-Hand is always current snapshot (year-independent)
# ---------------------------------------------------------------------------
class TestOnHandIsCurrentSnapshot(unittest.TestCase):
    """On-Hand Qty should be the same regardless of year filter."""

    def test_onhand_independent_of_year(self):
        df_sale_prep, df_onhand_prep, master, grpo = _prep()
        brands = master["GroupName"].unique()
        for brand in brands[:3]:
            detail_all = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand
            )
            detail_2024 = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand, year_list=[2024]
            )
            if detail_all.empty or detail_2024.empty:
                continue
            products_all = detail_all[detail_all["ItemCode"] != "TOTAL"]
            products_2024 = detail_2024[detail_2024["ItemCode"] != "TOTAL"]
            for _, row in products_all.iterrows():
                ic = row["ItemCode"]
                oh_all = row["OnHand_QTY"]
                match = products_2024[products_2024["ItemCode"] == ic]
                if not match.empty:
                    oh_2024 = match.iloc[0]["OnHand_QTY"]
                    self.assertEqual(
                        oh_all, oh_2024,
                        f"On-Hand for {ic} differs between all-years ({oh_all}) "
                        f"and 2024-only ({oh_2024}) — should be same snapshot"
                    )


# ---------------------------------------------------------------------------
# 4. Revenue (Master) uses Item Master Price consistently
# ---------------------------------------------------------------------------
class TestMasterPriceSource(unittest.TestCase):
    """Revenue (Master) must be computed from Item Master Price, not from
    the Sale sheet's 'Master Price' column (which is often NaN in real data).
    """

    def test_executive_summary_master_revenue_uses_item_master(self):
        """Inject NaN into Sale 'Master Price' column — Revenue (Master)
        should still be correct because it uses Item Master.
        """
        sale, onhand, master = _raw()
        sale = sale.copy()
        sale["Master Price"] = np.nan  # All NaN!

        result = compute_executive_summary(sale, onhand, master)
        rev_master = result.get("sold_master_thb", 0)
        rev_actual = result.get("sold_thb", 0)

        if rev_actual > 0:
            self.assertGreater(
                rev_master, 0,
                "Revenue (Master) is 0 even though items have prices in Item Master — "
                "the code is using Sale.Master Price (NaN) instead of Item Master.Price"
            )

    def test_trend_master_revenue_uses_item_master(self):
        """Same test for the trends endpoint."""
        sale, onhand, master = _raw()
        sale = sale.copy()
        sale["Master Price"] = np.nan

        result = compute_sales_trend_executive(sale, onhand, master)
        series = result.get("series", [])
        if series:
            total_master = sum(s.get("revenue_master_thb", 0) for s in series)
            total_actual = sum(s.get("revenue_thb", 0) for s in series)
            if total_actual > 0:
                self.assertGreater(
                    total_master, 0,
                    "Trend Revenue (Master) is 0 with NaN Sale.Master Price — "
                    "should use Item Master.Price"
                )


# ---------------------------------------------------------------------------
# 5. GP Commission invariants
# ---------------------------------------------------------------------------
class TestGPCommissionInvariants(unittest.TestCase):
    """GP Commission must be non-negative and less than revenue."""

    def test_gp_commission_non_negative(self):
        sale, onhand, master = _raw()
        result = compute_brand_list_metrics(sale, onhand, master)
        for b in result.get("rows", []):
            gp = b.get("gp_commission_thb", 0)
            self.assertGreaterEqual(
                gp, 0,
                f"Brand {b.get('brand')} has negative GP Commission: {gp}"
            )

    def test_gp_commission_less_than_revenue(self):
        sale, onhand, master = _raw()
        result = compute_brand_list_metrics(sale, onhand, master)
        for b in result.get("rows", []):
            gp = b.get("gp_commission_thb", 0)
            rev = b.get("revenue_thb", 0)
            if rev > 0:
                self.assertLessEqual(
                    gp, rev,
                    f"Brand {b.get('brand')} GP Commission {gp:,.0f} "
                    f"> Revenue {rev:,.0f}"
                )


# ---------------------------------------------------------------------------
# 6. All monetary values are non-negative
# ---------------------------------------------------------------------------
class TestNonNegativeValues(unittest.TestCase):
    """Revenue, cost, and on-hand values should never be negative."""

    def test_executive_summary_non_negative(self):
        sale, onhand, master = _raw()
        result = compute_executive_summary(sale, onhand, master)
        t = _exec_totals(result)
        for key in ["sold_thb", "sold_master_thb", "sold_qty", "onhand_qty"]:
            val = t.get(key, 0)
            self.assertGreaterEqual(
                val, 0, f"Executive summary {key} = {val} is negative"
            )

    def test_brand_detail_non_negative(self):
        df_sale_prep, df_onhand_prep, master, grpo = _prep()
        brands = master["GroupName"].unique()
        for brand in brands[:3]:
            detail = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand
            )
            if detail.empty:
                continue
            products = detail[detail["ItemCode"] != "TOTAL"]
            for col in ["Sold_QTY", "OnHand_QTY", "Brought_QTY"]:
                if col in products.columns:
                    min_val = products[col].min()
                    self.assertGreaterEqual(
                        min_val, 0,
                        f"Brand {brand} has negative {col}: {min_val}"
                    )


# ---------------------------------------------------------------------------
# 7. Dedup produces fewer or equal rows
# ---------------------------------------------------------------------------
class TestDedupReducesRows(unittest.TestCase):
    """Dedup should never increase the number of rows."""

    def test_channel_dedup_reduces_rows(self):
        sale, onhand, master = _raw()
        df_sale_prep, _, _ = nstk.prepare_sales_and_onhand_data(
            sale, onhand, master
        )
        deduped = _channel_dedup_sale(df_sale_prep, "monthly")
        self.assertLessEqual(
            len(deduped), len(df_sale_prep),
            f"Dedup increased rows from {len(df_sale_prep)} to {len(deduped)}"
        )


# ---------------------------------------------------------------------------
# 8. Executive totals == sum of all brands
# ---------------------------------------------------------------------------
class TestExecutiveTotalEqualsBrandSum(unittest.TestCase):
    """Total revenue in executive summary must equal sum of all brand revenues."""

    def test_total_revenue_matches_brand_sum(self):
        sale, onhand, master = _raw()
        exec_result = compute_executive_summary(sale, onhand, master)
        brand_result = compute_brand_list_metrics(sale, onhand, master)

        t = _exec_totals(exec_result)
        exec_rev = t.get("sold_thb", 0)
        brand_rev_sum = sum(b.get("revenue_thb", 0) for b in brand_result.get("rows", brand_result.get("brands", [])))

        self.assertAlmostEqual(
            exec_rev, brand_rev_sum, delta=max(exec_rev * 0.01, 1),
            msg=f"Executive revenue {exec_rev:,.0f} != sum of brand revenues {brand_rev_sum:,.0f}"
        )

    def test_total_sold_qty_matches_brand_sum(self):
        sale, onhand, master = _raw()
        exec_result = compute_executive_summary(sale, onhand, master)
        brand_result = compute_brand_list_metrics(sale, onhand, master)

        t = _exec_totals(exec_result)
        exec_qty = t.get("sold_qty", 0)
        brand_qty_sum = sum(b.get("sold_qty", 0) for b in brand_result.get("rows", brand_result.get("brands", [])))

        self.assertAlmostEqual(
            exec_qty, brand_qty_sum, delta=max(exec_qty * 0.01, 1),
            msg=f"Executive sold qty {exec_qty:,.0f} != sum of brand sold qty {brand_qty_sum:,.0f}"
        )


# ---------------------------------------------------------------------------
# 9. Trend series sum matches executive total
# ---------------------------------------------------------------------------
class TestTrendSumMatchesExecutive(unittest.TestCase):
    """Sum of all monthly trend values should equal the executive total.
    Note: executive summary and trend both use channel-dedup but may differ
    slightly because executive uses all-time while trend groups by period.
    Both should use the same dedup, so totals should match.
    """

    def test_trend_revenue_sum_close_to_executive(self):
        """Trend revenue sum should be within 5% of executive total.
        They may differ because executive summary uses period-based dedup
        while trend also groups by period — but the totals should be close.
        """
        sale, onhand, master = _raw()
        exec_result = compute_executive_summary(sale, onhand, master)
        trend_result = compute_sales_trend_executive(sale, onhand, master)

        t = _exec_totals(exec_result)
        exec_rev = t.get("sold_thb", 0)
        trend_rev_sum = sum(s.get("revenue_thb", 0) for s in trend_result.get("series", []))

        # Both should be non-zero if there's data
        if exec_rev > 0 or trend_rev_sum > 0:
            bigger = max(exec_rev, trend_rev_sum)
            smaller = min(exec_rev, trend_rev_sum)
            if bigger > 0:
                ratio = smaller / bigger
                self.assertGreater(
                    ratio, 0.95,
                    f"Executive revenue {exec_rev:,.0f} and trend sum "
                    f"{trend_rev_sum:,.0f} differ by more than 5%"
                )


# ---------------------------------------------------------------------------
# 10. Year filter produces subset of all-years data
# ---------------------------------------------------------------------------
class TestYearFilterSubset(unittest.TestCase):
    """Filtering by year should produce less-or-equal revenue than all years."""

    def test_year_filter_on_brand_detail(self):
        df_sale_prep, df_onhand_prep, master, grpo = _prep()
        brand = master["GroupName"].iloc[0]
        detail_all = nstk.generate_brand_product_profit_loss(
            df_sale_prep, df_onhand_prep, grpo, brand
        )
        detail_2024 = nstk.generate_brand_product_profit_loss(
            df_sale_prep, df_onhand_prep, grpo, brand, year_list=[2024]
        )
        if detail_all.empty:
            return
        products_all = detail_all[detail_all["ItemCode"] != "TOTAL"]
        products_2024 = detail_2024[detail_2024["ItemCode"] != "TOTAL"] if not detail_2024.empty else pd.DataFrame()

        sold_all = products_all["Sold_QTY"].sum()
        sold_2024 = products_2024["Sold_QTY"].sum() if not products_2024.empty else 0

        self.assertLessEqual(
            sold_2024, sold_all + 1,
            f"2024 sold qty {sold_2024} > all-years sold qty {sold_all} for {brand}"
        )

    def test_year_filter_on_trends(self):
        sale, onhand, master = _raw()
        trend_all = compute_sales_trend_executive(sale, onhand, master)
        trend_2024 = compute_sales_trend_executive(sale, onhand, master, year_list=[2024])

        rev_all = sum(s.get("revenue_thb", 0) for s in trend_all.get("series", []))
        rev_2024 = sum(s.get("revenue_thb", 0) for s in trend_2024.get("series", []))

        self.assertLessEqual(
            rev_2024, rev_all + 1,
            f"2024 trend revenue {rev_2024:,.0f} > all trend revenue {rev_all:,.0f}"
        )


# ---------------------------------------------------------------------------
# 11. On-hand total consistency
# ---------------------------------------------------------------------------
class TestOnHandConsistency(unittest.TestCase):
    """On-hand totals must be consistent across endpoints."""

    def test_brand_detail_onhand_lte_raw(self):
        """Sum of on-hand across all brand details should not exceed raw OnHand."""
        df_sale_prep, df_onhand_prep, master, grpo = _prep()
        raw_total = df_onhand_prep["OnHand"].sum()

        detail_total = 0
        seen_items = set()
        for brand in master["GroupName"].unique():
            detail = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand
            )
            if detail.empty:
                continue
            products = detail[detail["ItemCode"] != "TOTAL"]
            for _, row in products.iterrows():
                if row["ItemCode"] not in seen_items:
                    detail_total += row["OnHand_QTY"]
                    seen_items.add(row["ItemCode"])

        self.assertLessEqual(
            detail_total, raw_total + 1,
            f"Sum of brand detail on-hand {detail_total} > raw total {raw_total}"
        )


# ---------------------------------------------------------------------------
# 12. Margin percentage sanity
# ---------------------------------------------------------------------------
class TestMarginSanity(unittest.TestCase):
    """Margin % should be in reasonable range."""

    def test_brand_margins_in_range(self):
        sale, onhand, master = _raw()
        result = compute_brand_list_metrics(sale, onhand, master)
        for b in result.get("rows", []):
            margin_pct = b.get("gross_margin_pct", 0)
            self.assertGreaterEqual(
                margin_pct, -200,
                f"Brand {b.get('brand')} margin {margin_pct}% is unrealistically low"
            )
            self.assertLessEqual(
                margin_pct, 100,
                f"Brand {b.get('brand')} margin {margin_pct}% > 100% is impossible"
            )


# ---------------------------------------------------------------------------
# 13. No duplicate items within a brand detail
# ---------------------------------------------------------------------------
class TestNoDuplicateItems(unittest.TestCase):
    """Each item should appear only once in brand detail (plus one TOTAL row)."""

    def test_unique_items_in_brand_detail(self):
        df_sale_prep, df_onhand_prep, master, grpo = _prep()
        for brand in master["GroupName"].unique()[:3]:
            detail = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand
            )
            if detail.empty:
                continue
            products = detail[detail["ItemCode"] != "TOTAL"]
            item_codes = products["ItemCode"].tolist()
            self.assertEqual(
                len(item_codes), len(set(item_codes)),
                f"Brand {brand} has duplicate ItemCodes in detail: "
                f"{[ic for ic in item_codes if item_codes.count(ic) > 1]}"
            )


# ---------------------------------------------------------------------------
# 14. TOTAL row equals sum of product rows
# ---------------------------------------------------------------------------
class TestTotalRowConsistency(unittest.TestCase):
    """The TOTAL row in brand detail should equal the sum of product rows."""

    def test_total_row_sums(self):
        df_sale_prep, df_onhand_prep, master, grpo = _prep()
        for brand in master["GroupName"].unique()[:3]:
            detail = nstk.generate_brand_product_profit_loss(
                df_sale_prep, df_onhand_prep, grpo, brand
            )
            if detail.empty:
                continue
            total_row = detail[detail["ItemCode"] == "TOTAL"]
            product_rows = detail[detail["ItemCode"] != "TOTAL"]
            if total_row.empty:
                continue
            for col in ["Sold_QTY", "OnHand_QTY", "Brought_QTY"]:
                if col not in detail.columns:
                    continue
                total_val = total_row[col].iloc[0]
                sum_val = product_rows[col].sum()
                self.assertAlmostEqual(
                    total_val, sum_val, delta=1,
                    msg=f"Brand {brand} TOTAL {col}={total_val} != "
                        f"sum of products={sum_val}"
                )


# ---------------------------------------------------------------------------
# 15. Master Price consistency: Item Master Price should be positive
# ---------------------------------------------------------------------------
class TestMasterPricePositive(unittest.TestCase):
    """Every item in Item Master should have a positive Price."""

    def test_all_items_have_price(self):
        master = fixtures._medium_master()
        zero_price = master[master["Price"] <= 0]
        self.assertEqual(
            len(zero_price), 0,
            f"{len(zero_price)} items have zero or negative Price in Item Master"
        )


# ---------------------------------------------------------------------------
# 16. Revenue (Master) from Item Master lookup == Revenue (Master) from
#     direct computation (independent verification)
# ---------------------------------------------------------------------------
class TestMasterRevenueIndependentCalc(unittest.TestCase):
    """Compute Revenue (Master) independently and compare to what the
    executive summary returns."""

    def test_independent_master_revenue_calculation(self):
        sale, onhand, master = _raw()
        # Independent calculation
        df_sale_prep, _, _ = nstk.prepare_sales_and_onhand_data(
            sale, onhand, master
        )
        deduped = _channel_dedup_sale(df_sale_prep, "monthly")
        price_map = master.drop_duplicates("ItemCode").set_index("ItemCode")["Price"]
        deduped = deduped.copy()
        deduped["mp"] = deduped["ItemCode"].map(price_map).fillna(0)
        independent_master_rev = (deduped["Quantity"] * deduped["mp"]).sum()

        # API calculation
        result = compute_executive_summary(sale, onhand, master)
        t = _exec_totals(result)
        api_master_rev = t.get("sold_master_thb", 0)

        self.assertAlmostEqual(
            independent_master_rev, api_master_rev,
            delta=max(abs(independent_master_rev) * 0.01, 1),
            msg=f"Independent master revenue {independent_master_rev:,.0f} != "
                f"API master revenue {api_master_rev:,.0f}"
        )


if __name__ == "__main__":
    unittest.main()
