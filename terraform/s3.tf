resource "aws_s3_bucket" "config" {
  bucket        = local.config_bucket_name
  force_destroy = var.force_destroy_buckets
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "config" {
  bucket = aws_s3_bucket.config.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "config" {
  bucket = aws_s3_bucket.config.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "config" {
  bucket = aws_s3_bucket.config.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_notification" "config" {
  bucket = aws_s3_bucket.config.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.config_compiler.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = var.config_key
  }

  depends_on = [aws_lambda_permission.allow_config_bucket]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config" {
  bucket = aws_s3_bucket.config.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "sample_config" {
  count = var.manage_sample_config_object ? 1 : 0

  bucket       = aws_s3_bucket.config.id
  key          = var.config_key
  source       = "${path.module}/../examples/redirects.conf"
  etag         = filemd5("${path.module}/../examples/redirects.conf")
  content_type = "text/plain; charset=utf-8"

  depends_on = [
    aws_s3_bucket_versioning.config,
    aws_s3_bucket_notification.config,
  ]
}

resource "aws_lambda_invocation" "compile_sample_config" {
  count = var.manage_sample_config_object && var.invoke_compiler_after_config_apply ? 1 : 0

  function_name = aws_lambda_function.config_compiler.function_name

  input = jsonencode({
    Records = [
      {
        eventSource = "aws:s3"
        eventName   = "ObjectCreated:Put"
        s3 = {
          bucket = {
            name = aws_s3_bucket.config.bucket
          }
          object = {
            key = var.config_key
          }
        }
      }
    ]
  })

  triggers = {
    config_etag      = filemd5("${path.module}/../examples/redirects.conf")
    config_key       = var.config_key
    compiler_package = data.archive_file.config_compiler.output_base64sha256
  }

  depends_on = [
    aws_s3_object.sample_config,
    aws_iam_role_policy.config_compiler,
  ]
}

resource "aws_s3_bucket" "fallback" {
  bucket        = local.fallback_bucket_name
  force_destroy = var.force_destroy_buckets
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "fallback" {
  bucket = aws_s3_bucket.fallback.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "fallback" {
  bucket = aws_s3_bucket.fallback.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "fallback" {
  bucket = aws_s3_bucket.fallback.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "fallback_index" {
  bucket       = aws_s3_bucket.fallback.id
  key          = "index.html"
  content      = "<!doctype html><html><head><meta charset=\"utf-8\"><title>No redirect</title></head><body>No redirect rule matched this request.</body></html>"
  content_type = "text/html; charset=utf-8"
}

data "aws_iam_policy_document" "fallback_bucket" {
  statement {
    sid = "AllowCloudFrontReadFallbackOrigin"
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions = ["s3:GetObject"]

    resources = [
      "${aws_s3_bucket.fallback.arn}/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.redirect.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "fallback" {
  bucket = aws_s3_bucket.fallback.id
  policy = data.aws_iam_policy_document.fallback_bucket.json
}
