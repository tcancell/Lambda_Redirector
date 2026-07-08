data "archive_file" "redirect_lambda" {
  type        = "zip"
  output_path = "${path.module}/${local.lambda_function_name}.zip"

  source {
    filename = "handler.py"
    content  = file("${path.module}/../src/handler.py")
  }

  source {
    filename = "parser.py"
    content  = file("${path.module}/../src/parser.py")
  }

  source {
    filename = "matcher.py"
    content  = file("${path.module}/../src/matcher.py")
  }

  source {
    filename = "config_loader.py"
    content  = file("${path.module}/../src/config_loader.py")
  }

  source {
    filename = "response.py"
    content  = file("${path.module}/../src/response.py")
  }

  source {
    filename = "security.py"
    content  = file("${path.module}/../src/security.py")
  }

  source {
    filename = "settings.py"
    content = templatefile("${path.module}/settings.py.tftpl", {
      config_bucket                  = aws_s3_bucket.config.bucket
      config_key                     = var.config_key
      config_region                  = data.aws_region.current.region
      config_check_interval_seconds  = var.config_check_interval_seconds
      fallback_behavior              = var.fallback_behavior
      fallback_status_code           = var.fallback_status_code
      fallback_body                  = var.fallback_body
      redirect_cache_seconds         = var.redirect_cache_ttl_seconds
      edge_header_secret             = random_password.edge_header_secret.result
      allowed_redirect_hosts_csv     = local.allowed_redirect_hosts_csv
      require_https_redirect_targets = var.require_https_redirect_targets ? "True" : "False"
      max_redirect_config_bytes      = var.max_redirect_config_bytes
      enable_diagnostic_headers      = var.enable_diagnostic_headers ? "True" : "False"
    })
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  provider = aws.us_east_1

  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.us_east_1.arn
  tags              = local.common_tags
}

resource "aws_lambda_function" "redirect_engine" {
  provider = aws.us_east_1

  function_name           = local.lambda_function_name
  description             = "CloudFront Lambda@Edge Apache-style URL redirect engine"
  role                    = aws_iam_role.lambda_edge.arn
  handler                 = "handler.handler"
  runtime                 = var.lambda_runtime
  architectures           = ["x86_64"]
  memory_size             = var.lambda_memory_size
  timeout                 = var.lambda_timeout_seconds
  filename                = data.archive_file.redirect_lambda.output_path
  source_code_hash        = data.archive_file.redirect_lambda.output_base64sha256
  publish                 = true
  code_signing_config_arn = var.lambda_code_signing_config_arn != "" ? var.lambda_code_signing_config_arn : null
  tags                    = local.common_tags

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_edge,
  ]
}


data "archive_file" "config_compiler" {
  type        = "zip"
  output_path = "${path.module}/${local.resource_prefix}-config-compiler.zip"

  source {
    filename = "compiler_handler.py"
    content  = file("${path.module}/../src/compiler_handler.py")
  }

  source {
    filename = "compiler.py"
    content  = file("${path.module}/../src/compiler.py")
  }

  source {
    filename = "parser.py"
    content  = file("${path.module}/../src/parser.py")
  }

  source {
    filename = "security.py"
    content  = file("${path.module}/../src/security.py")
  }
}

resource "aws_cloudwatch_log_group" "config_compiler" {
  name              = "/aws/lambda/${local.resource_prefix}-config-compiler"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.regional.arn
  tags              = local.common_tags
}

resource "aws_lambda_function" "config_compiler" {
  function_name                  = "${local.resource_prefix}-config-compiler"
  description                    = "Compiles S3 Apache redirect config into CloudFront KeyValueStore fast-path rules"
  role                           = aws_iam_role.config_compiler.arn
  handler                        = "compiler_handler.handler"
  runtime                        = var.lambda_runtime
  architectures                  = ["x86_64"]
  memory_size                    = var.compiler_lambda_memory_size
  timeout                        = var.compiler_lambda_timeout_seconds
  reserved_concurrent_executions = var.compiler_reserved_concurrent_executions
  filename                       = data.archive_file.config_compiler.output_path
  source_code_hash               = data.archive_file.config_compiler.output_base64sha256
  kms_key_arn                    = aws_kms_key.regional.arn
  code_signing_config_arn        = var.lambda_code_signing_config_arn != "" ? var.lambda_code_signing_config_arn : null
  tags                           = local.common_tags

  dead_letter_config {
    target_arn = aws_sqs_queue.config_compiler_dlq.arn
  }

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      CONFIG_KEY                     = var.config_key
      KVS_ARN                        = aws_cloudfront_key_value_store.redirect_fastpath.arn
      ALLOWED_REDIRECT_HOSTS         = local.allowed_redirect_hosts_csv
      REQUIRE_HTTPS_REDIRECT_TARGETS = tostring(var.require_https_redirect_targets)
      MAX_REDIRECT_CONFIG_BYTES      = tostring(var.max_redirect_config_bytes)
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.config_compiler,
    aws_iam_role_policy.config_compiler,
  ]
}

resource "aws_lambda_permission" "allow_config_bucket" {
  statement_id  = "AllowExecutionFromRedirectConfigBucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.config_compiler.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.config.arn
}
