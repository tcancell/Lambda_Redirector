import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compiler import compile_text
from security import SecurityPolicy, SecurityValidationError


class SecurityValidationTests(unittest.TestCase):
    def test_rejects_http_absolute_targets_by_default(self):
        config = """
        <VirtualHost example.com>
          Redirect 301 / http://example.org/new
        </VirtualHost>
        """

        with self.assertRaises(SecurityValidationError):
            compile_text(config, SecurityPolicy())

    def test_allows_only_configured_absolute_redirect_hosts(self):
        config = """
        <VirtualHost example.com>
          Redirect 301 / https://evil.example/new
        </VirtualHost>
        """
        policy = SecurityPolicy.from_values(allowed_redirect_hosts="good.example")

        with self.assertRaises(SecurityValidationError):
            compile_text(config, policy)

    def test_rejects_protocol_relative_targets(self):
        config = """
        <VirtualHost example.com>
          Redirect 301 / //evil.example/new
        </VirtualHost>
        """

        with self.assertRaises(SecurityValidationError):
            compile_text(config, SecurityPolicy())

    def test_rejects_catastrophic_regex_shape(self):
        config = """
        <VirtualHost example.com>
          RedirectMatch 301 ^/(a+)+$ https://good.example/new
        </VirtualHost>
        """
        policy = SecurityPolicy.from_values(allowed_redirect_hosts="good.example")

        with self.assertRaises(SecurityValidationError):
            compile_text(config, policy)

    def test_allows_https_target_in_allowed_host_list(self):
        config = """
        <VirtualHost example.com>
          Redirect 301 / https://good.example/new
        </VirtualHost>
        """
        policy = SecurityPolicy.from_values(allowed_redirect_hosts="good.example")

        result = compile_text(config, policy)

        self.assertEqual(result.fast_rule_count, 1)


if __name__ == "__main__":
    unittest.main()
