import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from matcher import context_from_cloudfront_request
from response import fallback_response, redirect_response


class RedirectResponseTests(unittest.TestCase):
    def test_redirect_response_is_cloudfront_compatible(self):
        response = redirect_response(308, "https://example.com/new")

        self.assertEqual(response["status"], "308")
        self.assertEqual(response["statusDescription"], "Permanent Redirect")
        self.assertEqual(response["headers"]["location"][0]["value"], "https://example.com/new")
        self.assertEqual(response["headers"]["cache-control"][0]["value"], "public, max-age=300")
        self.assertEqual(response["headers"]["x-redirect-engine"][0]["value"], "lambda-edge")

    def test_redirect_response_can_disable_caching(self):
        response = redirect_response(302, "https://example.com/new", cache_seconds=0)

        self.assertEqual(response["headers"]["cache-control"][0]["value"], "no-store")

    def test_fallback_response(self):
        response = fallback_response(404, "No redirect rule matched this request.")

        self.assertEqual(response["status"], "404")
        self.assertEqual(response["headers"]["content-type"][0]["value"], "text/plain; charset=utf-8")
        self.assertEqual(response["headers"]["x-redirect-engine"][0]["value"], "lambda-edge")
        self.assertIn("No redirect", response["body"])

    def test_cloudfront_origin_request_context_prefers_redirect_host_header(self):
        request = {
            "method": "GET",
            "uri": "/old",
            "querystring": "",
            "headers": {
                "host": [{"key": "Host", "value": "fallback-bucket.s3.amazonaws.com"}],
                "x-redirect-host": [{"key": "X-Redirect-Host", "value": "Example.com"}],
            },
        }

        context = context_from_cloudfront_request(request)

        self.assertEqual(context.host, "example.com")

    def test_cloudfront_request_context_parses_host_path_query_and_headers(self):
        request = {
            "method": "GET",
            "uri": "/old",
            "querystring": "a=1",
            "headers": {
                "host": [{"key": "Host", "value": "Example.com"}],
                "cloudfront-forwarded-proto": [{"key": "CloudFront-Forwarded-Proto", "value": "https"}],
            },
        }

        context = context_from_cloudfront_request(request)

        self.assertEqual(context.host, "example.com")
        self.assertEqual(context.path, "/old")
        self.assertEqual(context.query, "a=1")
        self.assertEqual(context.scheme, "https")


if __name__ == "__main__":
    unittest.main()
