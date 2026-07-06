resource "aws_cloudfront_origin_access_control" "fallback" {
  name                              = "${local.resource_prefix}-fallback-oac"
  description                       = "OAC for the redirect platform fallback S3 origin"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_key_value_store" "redirect_fastpath" {
  name    = "${local.resource_prefix}-redirect-fastpath"
  comment = "Compiled fast-path redirect rules from the Apache-style S3 config"
}

resource "aws_cloudfront_cache_policy" "redirect" {
  name        = "${local.resource_prefix}-redirect-cache-policy"
  comment     = "Cache policy for host-aware redirect engine responses"
  default_ttl = var.redirect_cache_ttl_seconds
  max_ttl     = var.redirect_cache_ttl_seconds
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = false
    enable_accept_encoding_gzip   = false

    cookies_config {
      cookie_behavior = "none"
    }

    headers_config {
      header_behavior = "whitelist"

      headers {
        items = ["x-redirect-host"]
      }
    }

    query_strings_config {
      query_string_behavior = "all"
    }
  }
}

resource "aws_cloudfront_function" "viewer_context" {
  name    = "${local.resource_prefix}-viewer-context"
  runtime = "cloudfront-js-2.0"
  comment = "Fast-path redirect evaluator backed by CloudFront KeyValueStore"
  publish = true
  code = templatefile("${path.module}/../edge/fast_path.js.tftpl", {
    redirect_cache_seconds = var.redirect_cache_ttl_seconds
  })
  key_value_store_associations = [aws_cloudfront_key_value_store.redirect_fastpath.arn]
}

resource "aws_cloudfront_distribution" "redirect" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "AWS URL redirect and rewrite platform (${var.environment_name})"
  aliases             = []
  price_class         = var.cloudfront_price_class
  wait_for_deployment = var.wait_for_cloudfront_deployment
  default_root_object = "index.html"
  tags                = local.common_tags

  origin {
    domain_name              = aws_s3_bucket.fallback.bucket_regional_domain_name
    origin_id                = local.fallback_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.fallback.id

    s3_origin_config {
      origin_access_identity = ""
    }
  }

  default_cache_behavior {
    target_origin_id       = local.fallback_origin_id
    viewer_protocol_policy = var.viewer_protocol_policy
    cache_policy_id        = aws_cloudfront_cache_policy.redirect.id
    compress               = false

    allowed_methods = [
      "DELETE",
      "GET",
      "HEAD",
      "OPTIONS",
      "PATCH",
      "POST",
      "PUT",
    ]

    cached_methods = [
      "GET",
      "HEAD",
    ]

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.viewer_context.arn
    }

    lambda_function_association {
      event_type   = "origin-request"
      lambda_arn   = aws_lambda_function.redirect_engine.qualified_arn
      include_body = false
    }
  }

  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  lifecycle {
    ignore_changes = [
      aliases,
      viewer_certificate,
    ]
  }
}
