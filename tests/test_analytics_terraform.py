from pathlib import Path
import unittest


class AnalyticsTerraformTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.analytics_tf = (self.root / "terraform" / "analytics.tf").read_text()
        self.s3_tf = (self.root / "terraform" / "s3.tf").read_text()
        self.variables_tf = (self.root / "terraform" / "variables.tf").read_text()
        self.cloudfront_tf = (self.root / "terraform" / "cloudfront.tf").read_text()

    def test_v2_access_logs_are_parquet_and_hive_partitioned(self):
        self.assertIn('log_type     = "ACCESS_LOGS"', self.analytics_tf)
        self.assertIn('output_format = "parquet"', self.analytics_tf)
        self.assertIn("enable_hive_compatible_path = true", self.analytics_tf)
        self.assertIn('suffix_path                 = "{distributionid}/{yyyy}/{MM}/{dd}/{HH}"', self.analytics_tf)

    def test_athena_tracks_requested_url_ip_and_totals(self):
        self.assertIn('c_ip AS viewer_ip', self.analytics_tf)
        self.assertIn('AS requested_url', self.analytics_tf)
        self.assertIn('count(*) AS request_count', self.analytics_tf)
        self.assertIn('AS redirect_count', self.analytics_tf)

    def test_log_bucket_allows_v2_delivery_only_to_analytics_prefix(self):
        self.assertIn("AllowCloudFrontV2AccessLogDelivery", self.s3_tf)
        self.assertIn("delivery.logs.amazonaws.com", self.s3_tf)
        self.assertIn("DenyInsecureLogTransport", self.s3_tf)

    def test_analytics_has_cost_control_and_can_be_disabled(self):
        self.assertIn('variable "enable_redirect_analytics"', self.variables_tf)
        self.assertIn('variable "enable_legacy_cloudfront_access_logs"', self.variables_tf)
        self.assertIn('variable "analytics_query_bytes_scanned_cutoff"', self.variables_tf)
        self.assertIn("bytes_scanned_cutoff_per_query", self.analytics_tf)
        self.assertIn("enable_legacy_cloudfront_access_logs", self.cloudfront_tf)


if __name__ == "__main__":
    unittest.main()
