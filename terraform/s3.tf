resource "aws_s3_bucket" "config" {
  bucket        = local.config_bucket_name
  force_destroy = var.force_destroy_buckets
  tags          = local.common_tags
}


resource "aws_s3_bucket" "logs" {
  bucket        = substr("${local.resource_prefix}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.region}-logs", 0, 63)
  force_destroy = var.force_destroy_buckets
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket = aws_s3_bucket.logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "logs" {
  bucket = aws_s3_bucket.logs.id
  acl    = "log-delivery-write"

  depends_on = [
    aws_s3_bucket_ownership_controls.logs,
    aws_s3_bucket_public_access_block.logs,
  ]
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire-access-logs"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = var.access_log_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
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

resource "aws_s3_bucket_logging" "config" {
  bucket = aws_s3_bucket.config.id

  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "s3/config/"

  depends_on = [aws_s3_bucket_acl.logs]
}

resource "aws_s3_bucket_lifecycle_configuration" "config" {
  bucket = aws_s3_bucket.config.id

  rule {
    id     = "retain-current-and-expire-old-configs"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = var.config_noncurrent_version_retention_days
    }
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
      kms_master_key_id = aws_kms_key.regional.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

data "aws_iam_policy_document" "config_bucket" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.config.arn,
      "${aws_s3_bucket.config.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyUnencryptedConfigUploads"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:PutObject"]

    resources = [
      "${aws_s3_bucket.config.arn}/*",
    ]

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }
}

resource "aws_s3_bucket_policy" "config" {
  bucket = aws_s3_bucket.config.id
  policy = data.aws_iam_policy_document.config_bucket.json
}

resource "aws_s3_object" "sample_config" {
  count = var.manage_sample_config_object ? 1 : 0

  bucket                 = aws_s3_bucket.config.id
  key                    = var.config_key
  source                 = "${path.module}/../examples/redirects.conf"
  etag                   = filemd5("${path.module}/../examples/redirects.conf")
  content_type           = "text/plain; charset=utf-8"
  server_side_encryption = "aws:kms"
  kms_key_id             = aws_kms_key.regional.arn

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

resource "aws_s3_bucket_versioning" "fallback" {
  bucket = aws_s3_bucket.fallback.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_logging" "fallback" {
  bucket = aws_s3_bucket.fallback.id

  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "s3/fallback/"

  depends_on = [aws_s3_bucket_acl.logs]
}

resource "aws_s3_bucket_lifecycle_configuration" "fallback" {
  bucket = aws_s3_bucket.fallback.id

  rule {
    id     = "expire-fallback-noncurrent-versions"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "fallback" {
  bucket = aws_s3_bucket.fallback.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.regional.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_object" "fallback_index" {
  bucket                 = aws_s3_bucket.fallback.id
  key                    = "index.html"
  content                = <<-HTML
    <!doctype html><html><head><meta charset="utf-8"><title>No redirect</title></head><body>No redirect rule matched this request.</body></html>
  HTML
  content_type           = "text/html; charset=utf-8"
  server_side_encryption = "aws:kms"
  kms_key_id             = aws_kms_key.regional.arn
}

data "aws_iam_policy_document" "fallback_bucket" {
  statement {
    sid    = "DenyInsecureFallbackTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.fallback.arn,
      "${aws_s3_bucket.fallback.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyUnencryptedFallbackUploads"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:PutObject"]

    resources = [
      "${aws_s3_bucket.fallback.arn}/*",
    ]

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }

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
