import json
import logging
import threading
import unittest
import urllib.parse
import urllib.error
import urllib.request

import api
from tests.test_engine_rules import make_row


def call(base, path, method="GET"):
    request = urllib.request.Request(base + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read()), response.headers
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read()), error.headers
        finally:
            error.close()


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.CRITICAL)
        rows = [make_row("p1", "teint"), make_row("p2", "blush")]
        cls.server = api.make_server(rows, host="127.0.0.1", port=0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        logging.disable(logging.NOTSET)

    def test_health(self):
        status, body, _ = call(self.base, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["products"], 2)

    def test_recommend_success(self):
        status, body, headers = call(self.base, "/recommend?user_id=user_test")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "success")
        self.assertLessEqual(body["total_price"], body["budget"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_invalid_user_id_is_rejected(self):
        for bad in ("../etc/passwd", "a b", "x" * 80, ""):
            path = "/recommend?user_id=" + urllib.parse.quote(bad)
            status, _, _ = call(self.base, path)
            self.assertEqual(status, 400, bad)

    def test_unknown_user_returns_404(self):
        status, _, _ = call(self.base, "/recommend?user_id=inconnu")
        self.assertEqual(status, 404)

    def test_invalid_max_products_is_rejected(self):
        for bad in ("0", "7", "abc", "-1"):
            status, _, _ = call(self.base, f"/recommend?user_id=user_test&max_products={bad}")
            self.assertEqual(status, 400, bad)

    def test_unknown_route_and_method(self):
        self.assertEqual(call(self.base, "/nope")[0], 404)
        self.assertEqual(call(self.base, "/recommend?user_id=user_test", "POST")[0], 405)

    def test_metrics_counts_requests(self):
        call(self.base, "/health")
        status, body, _ = call(self.base, "/metrics")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(body["service"]["requests_total"], 1)


if __name__ == "__main__":
    unittest.main()