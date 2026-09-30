import unittest

import recommendation_engine as engine
from recommendation_engine import build_recommendation, is_compatible


def make_row(product_id, category="blush", price=10, skin=1, finish=1,
             available=1, user_id="user_test", budget=50, signal=""):
    return {
        "user_id": user_id,
        "product_id": product_id,
        "brand": "Marque",
        "name": f"Produit {product_id}",
        "category": category,
        "finish": "mat",
        "suitable_skin_type": "grasse",
        "preferred_finish": "mat",
        "price": str(price),
        "max_budget": str(budget),
        "skin_match": skin,
        "finish_match": finish,
        "available_flag": available,
        "interaction_signal": signal,
    }


class EngineRulesTest(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(engine.SCORE_WEIGHTS.values()), 1.0)

    def test_compatibility_rule_is_skin_or_finish(self):
        self.assertTrue(is_compatible({"skin_match": 1, "finish_match": 0}))
        self.assertTrue(is_compatible({"skin_match": 0, "finish_match": 1}))
        self.assertFalse(is_compatible({"skin_match": 0, "finish_match": 0}))

    def test_budget_is_strict_per_product_and_total(self):
        rows = [
            make_row("p1", "teint", price=30),
            make_row("p2", "blush", price=25),
            make_row("p3", "yeux", price=20),
            make_row("p4", "levres", price=60),
        ]
        result = build_recommendation("user_test", feature_rows=rows)
        ids = {p["product_id"] for p in result["routine"]}
        self.assertNotIn("p4", ids)
        self.assertLessEqual(result["total_price"], 50)

    def test_unavailable_products_are_excluded(self):
        rows = [make_row("p1", available=0), make_row("p2", "teint")]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertEqual([p["product_id"] for p in result["routine"]], ["p2"])

    def test_incompatible_products_are_excluded(self):
        rows = [make_row("p1", skin=0, finish=0), make_row("p2", "teint")]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertEqual([p["product_id"] for p in result["routine"]], ["p2"])
        self.assertFalse(result["fallbacks"]["skin_type"])

    def test_fallback_is_flagged_when_nothing_compatible(self):
        rows = [make_row("p1", skin=0, finish=0)]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertTrue(result["fallbacks"]["skin_type"])
        self.assertEqual(result["products_count"], 1)

    def test_no_duplicates_and_max_products(self):
        rows = [make_row(f"p{i}", "blush", price=5) for i in range(10)]
        result = build_recommendation("user_test", max_products=4, feature_rows=rows)
        ids = [p["product_id"] for p in result["routine"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLessEqual(len(ids), 4)

    def test_one_product_per_category_first(self):
        rows = [
            make_row("p1", "blush", price=5),
            make_row("p2", "blush", price=6),
            make_row("p3", "teint", price=7),
        ]
        result = build_recommendation("user_test", max_products=2, feature_rows=rows)
        categories = {p["category"] for p in result["routine"]}
        self.assertEqual(categories, {"blush", "teint"})

    def test_unknown_user_raises(self):
        with self.assertRaises(ValueError):
            build_recommendation("inconnu", feature_rows=[make_row("p1")])

    def test_excluded_products_are_not_recommended(self):
        rows = [make_row("p1", "teint"), make_row("p2", "blush")]
        result = build_recommendation(
            "user_test", feature_rows=rows, exclude_product_ids={"p1"}
        )
        self.assertNotIn("p1", {p["product_id"] for p in result["routine"]})

    def test_result_is_deterministic(self):
        rows = [make_row(f"p{i}", "blush", price=5 + i) for i in range(6)]
        first = build_recommendation("user_test", feature_rows=rows)
        second = build_recommendation("user_test", feature_rows=rows)
        self.assertEqual(
            [p["product_id"] for p in first["routine"]],
            [p["product_id"] for p in second["routine"]],
        )

    def test_every_product_has_explanations_and_valid_score(self):
        rows = [make_row("p1", "teint"), make_row("p2", "blush")]
        result = build_recommendation("user_test", feature_rows=rows)
        for product in result["routine"]:
            self.assertGreaterEqual(len(product["reasons"]), 3)
            self.assertTrue(0 <= product["score"] <= 1)


if __name__ == "__main__":
    unittest.main()