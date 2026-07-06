import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from matcher import RequestContext, find_match
from parser import parse_config


class RewriteConditionTests(unittest.TestCase):
    def test_host_and_uri_conditions_must_match(self):
        config = parse_config(
            """
            <VirtualHost *>
              RewriteCond %{HTTP_HOST} ^example\\.com$ [NC]
              RewriteCond %{REQUEST_URI} ^/legacy
              RewriteRule ^/legacy/(.*)$ https://www.example.com/new/$1 [R=301,L]
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="Example.com", path="/legacy/page"))

        self.assertEqual(result.status, 301)
        self.assertEqual(result.location, "https://www.example.com/new/page")
        self.assertIsNone(find_match(config, RequestContext(host="other.com", path="/legacy/page")))

    def test_query_string_condition(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              RewriteCond %{QUERY_STRING} (^|&)ref=old($|&)
              RewriteRule ^/landing$ /landing-new [R=302,L,QSA]
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="example.com", path="/landing", query="ref=old&x=1"))

        self.assertEqual(result.status, 302)
        self.assertEqual(result.location, "/landing-new?ref=old&x=1")

    def test_header_condition_and_or_flag(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              RewriteCond %{HTTP:X-Preview} =1 [OR]
              RewriteCond %{HTTP_USER_AGENT} PreviewBot
              RewriteRule ^/private$ /preview [R=307,L,QSD]
            </VirtualHost>
            """
        )

        result = find_match(
            config,
            RequestContext(
                host="example.com",
                path="/private",
                query="x=1",
                headers={"user-agent": ["PreviewBot/1.0"]},
            ),
        )

        self.assertEqual(result.status, 307)
        self.assertEqual(result.location, "/preview")

    def test_scheme_condition(self):
        config = parse_config(
            """
            <VirtualHost example.com>
              RewriteCond %{REQUEST_SCHEME} =http
              RewriteRule ^/(.*)$ https://example.com/$1 [R=308,L]
            </VirtualHost>
            """
        )

        result = find_match(config, RequestContext(host="example.com", path="/abc", scheme="https"))
        self.assertIsNone(result)
        redirect = find_match(config, RequestContext(host="example.com", path="/abc", scheme="http"))
        self.assertEqual(redirect.status, 308)
        self.assertEqual(redirect.location, "https://example.com/abc")


if __name__ == "__main__":
    unittest.main()
