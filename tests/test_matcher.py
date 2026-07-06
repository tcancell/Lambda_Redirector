import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from matcher import RequestContext, find_match
from parser import parse_config


class MatcherTests(unittest.TestCase):
    def test_redirect_prefix_appends_remainder_and_query(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              Redirect 301 /old /new
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="example.com", path="/old/path", query="a=1"))

        self.assertEqual(result.status, 301)
        self.assertEqual(result.location, "/new/path?a=1")

    def test_redirect_match_expands_backreference(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              RedirectMatch 301 ^/blog/(.*)$ /articles/$1
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="example.com", path="/blog/post"))

        self.assertEqual(result.location, "/articles/post")

    def test_wildcard_redirect_discards_query_with_flag(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              Redirect 302 /promo/* /campaigns/$1 [QSD]
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="example.com", path="/promo/summer", query="utm=1"))

        self.assertEqual(result.status, 302)
        self.assertEqual(result.location, "/campaigns/summer")

    def test_host_alias_matching(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              ServerAlias *.example.net
              Redirect 301 /old /new
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="docs.example.net", path="/old"))

        self.assertEqual(result.location, "/new")

    def test_rewrite_rule_can_internal_rewrite(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              RewriteRule ^/docs/(.*)$ /content/$1 [L]
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="example.com", path="/docs/readme", query="v=1"))

        self.assertEqual(result.action, "rewrite")
        self.assertEqual(result.uri, "/content/readme")
        self.assertEqual(result.querystring, "v=1")


if __name__ == "__main__":
    unittest.main()
