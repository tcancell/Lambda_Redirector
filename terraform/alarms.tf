resource "aws_cloudwatch_metric_alarm" "lambda_edge_errors" {
  provider = aws.us_east_1

  alarm_name          = "${local.resource_prefix}-lambda-edge-errors"
  alarm_description   = "Lambda@Edge redirect engine reported errors in us-east-1. Edge replica errors can appear in regional log groups."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.redirect_engine.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_edge_throttles" {
  provider = aws.us_east_1

  alarm_name          = "${local.resource_prefix}-lambda-edge-throttles"
  alarm_description   = "Lambda@Edge redirect engine throttles in us-east-1."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = aws_lambda_function.redirect_engine.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "config_compiler_errors" {
  alarm_name          = "${local.resource_prefix}-config-compiler-errors"
  alarm_description   = "S3-triggered config compiler reported errors."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.config_compiler.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "config_compiler_throttles" {
  alarm_name          = "${local.resource_prefix}-config-compiler-throttles"
  alarm_description   = "S3-triggered config compiler throttles."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = aws_lambda_function.config_compiler.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "cloudfront_5xx_rate" {
  provider = aws.us_east_1

  alarm_name          = "${local.resource_prefix}-cloudfront-5xx-rate"
  alarm_description   = "CloudFront 5xx error rate is above the configured threshold."
  namespace           = "AWS/CloudFront"
  metric_name         = "5xxErrorRate"
  dimensions          = { DistributionId = aws_cloudfront_distribution.redirect.id, Region = "Global" }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 5
  threshold           = 1
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions
  tags                = local.common_tags
}
