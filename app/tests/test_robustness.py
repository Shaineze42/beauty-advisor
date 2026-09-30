import math
import unittest

from recommendation_engine import build_recommendation
from tests.test_engine_rules import make_row


class RobustnessTest(unittest.TestCase):
    def test_missing_price_is_ignored_without_crash(self):
        rows = [make_row("p1", "teint", price=""), make_row("p2", "blush")]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertEqual([p["product_id"] for p in result["routine"]], ["p2"])

    def test_non_numeric_price_is_ignored(self):
        rows = [make_row("p1", "teint", price="abc"), make_row("p2", "blush")]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertNotIn("p1", {p["product_id"] for p in result["routine"]})

    def test_invalid_budget_is_flagged_as_fallback(self):
        rows = [make_row("p1", "teint", budget="")]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertTrue(result["fallbacks"]["budget"])

    def test_nan_values_do_not_crash(self):
        row = make_row("p1", "teint")
        row["skin_match"] = math.nan
        row["finish_match"] = 1
        result = build_recommendation("user_test", feature_rows=[row])
        self.assertIn(result["status"], {"success", "no_compatible_product"})

    def test_all_products_unavailable_returns_clean_status(self):
        rows = [make_row("p1", available=0), make_row("p2", "teint", available=0)]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertEqual(result["status"], "no_compatible_product")
        self.assertEqual(result["products_count"], 0)

    def test_everything_above_budget_returns_clean_result(self):
        rows = [make_row("p1", price=500), make_row("p2", "teint", price=600)]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertLessEqual(result["total_price"], result["budget"])

    def test_duplicate_rows_do_not_duplicate_products(self):
        rows = [make_row("p1", "teint"), make_row("p1", "teint")]
        result = build_recommendation("user_test", feature_rows=rows)
        ids = [p["product_id"] for p in result["routine"]]
        self.assertEqual(ids, ["p1"])

    def test_empty_dataset_raises_clear_error(self):
        with self.assertRaises(ValueError):
            build_recommendation("user_test", feature_rows=[])

    def test_accents_and_unknown_signal_are_handled(self):
        row = make_row("p1", "lèvres", signal="valeur_inconnue")
        result = build_recommendation("user_test", feature_rows=[row])
        self.assertEqual(result["products_count"], 1)

    def test_large_catalog_stays_fast(self):
        rows = [make_row(f"p{i}", "blush", price=5) for i in range(5000)]
        result = build_recommendation("user_test", feature_rows=rows)
        self.assertLessEqual(result["products_count"], 4)


if __name__ == "__main__":
    unittest.main()