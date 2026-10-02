"""Tests du document `routines` (sans base de données)."""
import unittest
from datetime import datetime, timezone

from recommendation_engine import build_recommendation
from tests.test_engine_rules import make_row
from save_routines_mongo import (
    build_routine_document,
    request_budget_of,
    routine_id_for,
    rows_with_request_budget,
)


class RoutineDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        categories = ["teint", "blush", "yeux", "levres"]
        cls.rows = [
            make_row(f"p{i}", category=categories[i % 4], price=8 + i * 3,
                     user_id=user, budget=100)
            for user in ("user_001", "user_002")
            for i in range(8)
        ]

    def test_routine_id_is_deterministic(self):
        self.assertEqual(routine_id_for("user_001"), "routine_user_001")

    def test_document_has_expected_fields_and_no_personal_data(self):
        result = build_recommendation("user_001", feature_rows=self.rows)
        doc = build_routine_document(
            result,
            request_id="request_001",
            created_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
        for field in (
            "routine_id", "request_id", "user_id", "budget", "total_price",
            "products", "fallbacks", "model_version", "created_at",
        ):
            self.assertIn(field, doc)
        self.assertEqual(doc["user_id"], "user_001")
        self.assertEqual(doc["products_count"], len(doc["products"]))
        self.assertLessEqual(doc["total_price"], doc["budget"])
        for product in doc["products"]:
            self.assertTrue(product["reasons"])

    def test_same_user_gives_same_id_so_upsert_is_idempotent(self):
        first = build_recommendation("user_002", feature_rows=self.rows)
        second = build_recommendation("user_002", feature_rows=self.rows)
        self.assertEqual(
            build_routine_document(first)["routine_id"],
            build_routine_document(second)["routine_id"],
        )

    def test_request_budget_is_enforced_without_mutating_source(self):
        original = [dict(row) for row in self.rows]
        adjusted = rows_with_request_budget(self.rows, "user_001", 50)
        result = build_recommendation("user_001", feature_rows=adjusted)
        self.assertEqual(result["budget"], 50.0)
        if not result["fallbacks"]["budget"]:
            self.assertLessEqual(result["total_price"], 50.0)
        self.assertEqual(self.rows, original)

    def test_request_budget_is_read_from_context(self):
        request = {"request_id": "r1", "context": {"budget": 50}}
        self.assertEqual(request_budget_of(request), 50.0)

    def test_request_budget_flat_field_and_invalid_values(self):
        self.assertEqual(request_budget_of({"budget": "60"}), 60.0)
        self.assertIsNone(request_budget_of(None))
        self.assertIsNone(request_budget_of({"context": {}}))
        self.assertIsNone(request_budget_of({"context": {"budget": "abc"}}))
        self.assertIsNone(request_budget_of({"context": {"budget": -5}}))

    def test_budget_source_is_recorded(self):
        result = build_recommendation("user_001", feature_rows=self.rows)
        self.assertEqual(build_routine_document(result)["budget_source"], "profile")
        self.assertEqual(
            build_routine_document(result, budget_source="request")["budget_source"],
            "request",
        )

    def test_no_request_keeps_profile_budget(self):
        self.assertIs(
            rows_with_request_budget(self.rows, "user_001", None), self.rows
        )


if __name__ == "__main__":
    unittest.main()