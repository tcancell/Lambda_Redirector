import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compiler import compile_text


class CompilerTests(unittest.TestCase):
    def test_example_config_compiles_fast_path_hosts(self):
        config_path = Path(__file__).resolve().parents[1] / "examples" / "redirects.conf"
        result = compile_text(config_path.read_text())

        self.assertIn("h:tcancell.test.gwu.edu", result.kvs)
        self.assertIn("h:lamred.test.gwu.edu", result.kvs)
        self.assertIn("h:www.lamred.test.gwu.edu", result.kvs)
        self.assertIn("h:redirector.test.gwu.edu", result.kvs)
        self.assertGreaterEqual(result.fast_rule_count, 3)

    def test_supported_rewritecond_stays_fast_path(self):
        result = compile_text(
            """
            <VirtualHost example.com>
              RewriteCond %{HTTP_HOST} ^example\\.com$ [NC]
              RewriteCond %{QUERY_STRING} (^|&)ref=old($|&) [OR]
              RewriteCond %{REQUEST_URI} ^/legacy
              RewriteRule ^/legacy/(.*)$ https://www.example.com/new/$1 [R=301,L,QSD]
            </VirtualHost>
            """
        )
        rules = json.loads(result.kvs["h:example.com"])

        self.assertEqual(rules[0]["t"], "rewrite")
        self.assertEqual(len(rules[0]["c"]), 3)
        self.assertEqual(result.fallback_rule_count, 0)

    def test_compiler_stops_after_first_fallback_rule_to_preserve_order(self):
        result = compile_text(
            """
            <VirtualHost example.com>
              Redirect 301 /a /b
              RewriteRule ^/internal/(.*)$ /origin/$1 [L]
              Redirect 301 /after /later
            </VirtualHost>
            """
        )
        rules = json.loads(result.kvs["h:example.com"])

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["src"], "/a")
        self.assertEqual(result.fast_rule_count, 1)
        self.assertEqual(result.fallback_rule_count, 2)

    def test_wildcard_virtualhost_stays_fallback(self):
        result = compile_text(
            """
            <VirtualHost *.example.com>
              Redirect 301 /a /b
            </VirtualHost>
            """
        )

        self.assertNotIn("h:*.example.com", result.kvs)
        self.assertEqual(result.fast_rule_count, 0)
        self.assertEqual(result.fallback_rule_count, 1)


if __name__ == "__main__":
    unittest.main()
