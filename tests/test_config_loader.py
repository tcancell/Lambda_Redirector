import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config_loader import S3ConfigLoader


class _Body:
    def __init__(self, text):
        self.text = text

    def read(self):
        return self.text.encode("utf-8")


class _FakeS3:
    def __init__(self, text):
        self.text = text
        self.head_calls = 0
        self.get_calls = 0

    def head_object(self, Bucket, Key):
        self.head_calls += 1
        return {"ETag": "v1", "VersionId": "1", "LastModified": "Thu, 02 Jul 2026 00:00:00 GMT"}

    def get_object(self, Bucket, Key):
        self.get_calls += 1
        return {
            "Body": _Body(self.text),
            "ETag": "v1",
            "VersionId": "1",
            "LastModified": "Thu, 02 Jul 2026 00:00:00 GMT",
        }


class ConfigLoaderTests(unittest.TestCase):
    def test_initial_load_fetches_config_without_head_request(self):
        s3 = _FakeS3("""
        <VirtualHost example.com>
          Redirect 301 /old /new
        </VirtualHost>
        """)
        loader = S3ConfigLoader("bucket", "redirects.conf", "us-east-1", 0, s3_client=s3)

        config = loader.get_config()

        self.assertEqual(len(config.virtual_hosts), 1)
        self.assertEqual(s3.head_calls, 0)
        self.assertEqual(s3.get_calls, 1)

    def test_later_load_checks_fingerprint_before_refetching(self):
        s3 = _FakeS3("""
        <VirtualHost example.com>
          Redirect 301 /old /new
        </VirtualHost>
        """)
        loader = S3ConfigLoader("bucket", "redirects.conf", "us-east-1", 0, s3_client=s3)

        loader.get_config()
        loader.get_config()

        self.assertEqual(s3.head_calls, 1)
        self.assertEqual(s3.get_calls, 1)


if __name__ == "__main__":
    unittest.main()
