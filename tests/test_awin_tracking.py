import json
import sqlite3
import unittest

from src.awin_tracking import (
    AwinLinkBuilderClient,
    TrackingLinkCache,
    build_click_parameters,
    resolve_tracking_url,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RecordingOpener:
    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse({"url": "https://www.awin1.com/tracked"})


class FakeClient:
    def __init__(self):
        self.calls = 0

    def generate(self, advertiser_id, destination_url, parameters):
        self.calls += 1
        return "https://www.awin1.com/from-client"


class AwinTrackingTests(unittest.TestCase):
    def test_click_parameters_contain_no_user_text(self):
        parameters = build_click_parameters(42, 3, "search")
        self.assertEqual(parameters["clickref2"], "product-42")
        self.assertEqual(parameters["clickref3"], "position-3")
        self.assertNotIn("query", " ".join(parameters.values()).lower())

    def test_client_uses_bearer_auth_and_expected_payload(self):
        opener = RecordingOpener()
        client = AwinLinkBuilderClient(999, "secret-token", opener=opener)
        result = client.generate(
            123,
            "https://merchant.test/product",
            {"clickref": "trovai-search"},
        )
        self.assertEqual(result, "https://www.awin1.com/tracked")
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["advertiserId"], 123)
        self.assertEqual(payload["destinationUrl"], "https://merchant.test/product")
        self.assertEqual(timeout, 10)

    def test_resolver_reuses_cached_link(self):
        conn = sqlite3.connect(":memory:")
        client = FakeClient()
        parameters = {"clickref": "test"}
        first = resolve_tracking_url(
            conn, client, 123, "https://merchant.test/product", parameters
        )
        second = resolve_tracking_url(
            conn, client, 123, "https://merchant.test/product", parameters
        )
        self.assertEqual(first, second)
        self.assertEqual(client.calls, 1)

    def test_cache_key_changes_with_position(self):
        first = TrackingLinkCache.cache_key(1, "https://example.test", {"p": "1"})
        second = TrackingLinkCache.cache_key(1, "https://example.test", {"p": "2"})
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
