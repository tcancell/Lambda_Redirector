import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parser import ConfigParseError, RedirectMatchRule, RedirectRule, RewriteRule, parse_config


class ParserTests(unittest.TestCase):
    def test_parses_virtual_hosts_and_rules_in_order(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              ServerAlias www.example.com *.example.net
              Redirect 301 /old-page /new-page
              RedirectMatch 302 ^/blog/(.*)$ /articles/$1 [QSD]
              RewriteCond %{HTTP_HOST} ^example\\.com$
              RewriteCond %{REQUEST_URI} ^/legacy
              RewriteRule ^/legacy/(.*)$ https://www.example.com/new/$1 [R=301,L]
            </VirtualHost>
            """
        )

        self.assertEqual(len(config.virtual_hosts), 1)
        vhost = config.virtual_hosts[0]
        self.assertEqual(vhost.host_patterns, ["example.com", "www.example.com", "*.example.net"])
        self.assertIsInstance(vhost.rules[0], RedirectRule)
        self.assertIsInstance(vhost.rules[1], RedirectMatchRule)
        self.assertIsInstance(vhost.rules[2], RewriteRule)
        self.assertEqual(len(vhost.rules[2].conditions), 2)
        self.assertEqual(vhost.rules[2].flags["r"], "301")

    def test_rejects_unsupported_status(self):
        with self.assertRaises(ConfigParseError):
            parse_config(
                """
                <VirtualHost example.com>
                  Redirect 305 /old /new
                </VirtualHost>
                """
            )

    def test_rejects_unsupported_rewrite_redirect_status(self):
        with self.assertRaises(ConfigParseError):
            parse_config(
                """
                <VirtualHost example.com>
                  RewriteRule ^/old$ /new [R=305]
                </VirtualHost>
                """
            )

    def test_preserves_regex_backslashes(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              RewriteCond %{HTTP_HOST} ^example\\.com$
              RewriteRule ^/x$ /y [R=301]
            </VirtualHost>
            """
        )

        condition = config.virtual_hosts[0].rules[0].conditions[0]
        self.assertEqual(condition.pattern, r"^example\.com$")

    def test_example_redirect_config_parses(self):
        config_path = Path(__file__).resolve().parents[1] / "examples" / "redirects.conf"
        config = parse_config(config_path.read_text())

        self.assertEqual(len(config.virtual_hosts), 3)

    def test_preserves_quoted_regex_backslashes(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              RewriteCond "%{HTTP_HOST}" "^example\\.com$"
              RewriteRule ^/x$ /y [R=301]
            </VirtualHost>
            """
        )

        condition = config.virtual_hosts[0].rules[0].conditions[0]
        self.assertEqual(condition.pattern, r"^example\.com$")


if __name__ == "__main__":
    unittest.main()
