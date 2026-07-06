"""Local defaults. Terraform replaces this module inside the Lambda@Edge zip."""

CONFIG_BUCKET = ""
CONFIG_KEY = "redirects.conf"
CONFIG_REGION = "us-east-1"
CONFIG_CHECK_INTERVAL_SECONDS = 30
FALLBACK_BEHAVIOR = "not_found"
FALLBACK_STATUS_CODE = 404
FALLBACK_BODY = "No redirect rule matched this request."
REDIRECT_CACHE_SECONDS = 300
