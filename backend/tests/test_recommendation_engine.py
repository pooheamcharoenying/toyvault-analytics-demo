"""Tests for the rule-based recommendation engine (OBJ-86 Layer 1)."""
import unittest
import tests.conftest  # noqa: F401

from app.utils import recommendation_engine as reng


class TestBrandRecommendations(unittest.TestCase):
    """Tests for recommend_for_brand()."""

    def _products_with_dead_stock(self):
        return [
            {"ItemCode": "A1", "Description": "Widget", "Sold_QTY": 100, "OnHand_QTY": 50,
             "Actual_Revenue_THB": 10000, "Total_Cost_THB": 5000, "Profit_Loss_THB": 5000,
             "Profit_Margin_%": 50, "Master_Price": 100},
            {"ItemCode": "A2", "Description": "Gadget", "Sold_QTY": 0, "OnHand_QTY": 200,
             "Actual_Revenue_THB": 0, "Total_Cost_THB": 0, "Profit_Loss_THB": 0,
             "Profit_Margin_%": 0, "Master_Price": 50},
        ]

    def test_returns_list(self):
        recs = reng.recommend_for_brand("TestBrand", self._products_with_dead_stock())
        self.assertIsInstance(recs, list)

    def test_dead_stock_recommendation(self):
        recs = reng.recommend_for_brand("TestBrand", self._products_with_dead_stock())
        dead_recs = [r for r in recs if r["rule_id"] == "R-01"]
        self.assertGreater(len(dead_recs), 0, "Should flag dead stock")
        self.assertIn("A2", dead_recs[0]["text"])

    def test_recommendation_fields(self):
        recs = reng.recommend_for_brand("TestBrand", self._products_with_dead_stock())
        for rec in recs:
            self.assertIn("rule_id", rec)
            self.assertIn("severity", rec)
            self.assertIn("title", rec)
            self.assertIn("text", rec)
            self.assertIn("source", rec)
            self.assertEqual(rec["source"], "rule")
            self.assertIn(rec["severity"], ("critical", "warning", "info"))

    def test_empty_products(self):
        recs = reng.recommend_for_brand("TestBrand", [])
        self.assertEqual(recs, [])

    def test_max_7_recommendations(self):
        # Many products to generate multiple rules
        products = [
            {"ItemCode": f"P{i}", "Sold_QTY": 0 if i > 3 else i,
             "OnHand_QTY": 100, "Actual_Revenue_THB": i * 100 if i <= 3 else 0,
             "Total_Cost_THB": i * 50, "Profit_Loss_THB": -100,
             "Profit_Margin_%": -10, "Master_Price": 100}
            for i in range(20)
        ]
        recs = reng.recommend_for_brand("TestBrand", products)
        self.assertLessEqual(len(recs), 7)

    def test_unhealthy_portfolio_triggered(self):
        """R-07: >60% D/E products should trigger warning."""
        products = []
        # 1 star product (A class — contributes 80% revenue)
        products.append({"ItemCode": "STAR", "Sold_QTY": 100, "OnHand_QTY": 10,
                         "Actual_Revenue_THB": 80000, "Total_Cost_THB": 20000,
                         "Profit_Loss_THB": 60000, "Master_Price": 100})
        # 9 weak products (D/E class)
        for i in range(9):
            products.append({"ItemCode": f"WEAK{i}", "Sold_QTY": 1, "OnHand_QTY": 50,
                             "Actual_Revenue_THB": 100, "Total_Cost_THB": 80,
                             "Profit_Loss_THB": 20, "Master_Price": 100})
        recs = reng.recommend_for_brand("TestBrand", products)
        portfolio_recs = [r for r in recs if r["rule_id"] == "R-07"]
        self.assertGreater(len(portfolio_recs), 0, "Should flag unhealthy portfolio")


class TestLocationRecommendations(unittest.TestCase):
    """Tests for recommend_for_location()."""

    def test_underperforming_location(self):
        metrics = {
            "sold_thb": 100000, "onhand_thb": 500000,
            "revenue_per_thb_inventory": 0.2,
            "sell_through_rate": 10, "dead_stock_pct": 45,
            "dead_stock_thb": 225000, "days_cover": 300,
            "health_score": 25, "abcde_class": "D",
        }
        avg = {"revenue_per_thb_inventory": 1.5}
        recs = reng.recommend_for_location("Bad Store", metrics, avg)
        self.assertGreater(len(recs), 0)
        rule_ids = [r["rule_id"] for r in recs]
        self.assertIn("R-04", rule_ids)

    def test_star_location(self):
        metrics = {
            "sold_thb": 5000000, "onhand_thb": 500000,
            "revenue_per_thb_inventory": 10.0,
            "sell_through_rate": 80, "dead_stock_pct": 2,
            "dead_stock_thb": 10000, "days_cover": 20,
            "health_score": 95, "abcde_class": "A",
        }
        avg = {"revenue_per_thb_inventory": 1.5}
        recs = reng.recommend_for_location("Star Store", metrics, avg)
        star_recs = [r for r in recs if r["rule_id"] == "R-05"]
        self.assertGreater(len(star_recs), 0, "Should flag star location")

    def test_recommendation_fields(self):
        metrics = {"sold_thb": 100000, "onhand_thb": 500000,
                   "revenue_per_thb_inventory": 0.2, "sell_through_rate": 10,
                   "dead_stock_pct": 45, "dead_stock_thb": 225000,
                   "days_cover": 300, "health_score": 25}
        recs = reng.recommend_for_location("Store", metrics, {"revenue_per_thb_inventory": 1.5})
        for rec in recs:
            self.assertIn("rule_id", rec)
            self.assertIn("severity", rec)
            self.assertEqual(rec["source"], "rule")


class TestItemRecommendations(unittest.TestCase):
    """Tests for recommend_for_item()."""

    def test_dead_stock_item(self):
        info = {"item_code": "DEAD1", "item_name": "Dead Widget", "brand": "BrandA",
                "total_onhand_qty": 500, "total_onhand_thb": 50000,
                "total_sold_qty": 0, "total_sold_thb": 0,
                "abcde_class_in_brand": "E"}
        locs = [{"whs_name": "WH01", "onhand_qty": 500, "lifetime_sold_qty": 0, "lifetime_sold_thb": 0}]
        recs = reng.recommend_for_item(info, locs)
        dead_recs = [r for r in recs if r["rule_id"] == "R-01"]
        self.assertGreater(len(dead_recs), 0, "Should flag dead stock item")

    def test_stock_imbalance(self):
        info = {"item_code": "A1", "item_name": "Widget", "brand": "BrandA",
                "total_onhand_qty": 200, "total_onhand_thb": 20000,
                "total_sold_qty": 50, "total_sold_thb": 5000,
                "abcde_class_in_brand": "B"}
        locs = [
            {"whs_name": "Good Store", "onhand_qty": 50, "lifetime_sold_qty": 50, "lifetime_sold_thb": 5000},
            {"whs_name": "Bad Store", "onhand_qty": 150, "lifetime_sold_qty": 0, "lifetime_sold_thb": 0},
        ]
        recs = reng.recommend_for_item(info, locs)
        imbalance_recs = [r for r in recs if r["rule_id"] == "R-03"]
        self.assertGreater(len(imbalance_recs), 0, "Should flag stock imbalance")
        self.assertIn("Good Store", imbalance_recs[0]["text"])
        self.assertIn("Bad Store", imbalance_recs[0]["text"])

    def test_ab_class_info(self):
        info = {"item_code": "A1", "item_name": "Widget", "brand": "BrandA",
                "total_onhand_qty": 50, "total_onhand_thb": 5000,
                "total_sold_qty": 100, "total_sold_thb": 10000,
                "abcde_class_in_brand": "A"}
        recs = reng.recommend_for_item(info, [])
        info_recs = [r for r in recs if r["rule_id"] == "R-INFO-02"]
        self.assertGreater(len(info_recs), 0, "Should show A-class info")


if __name__ == "__main__":
    unittest.main()
