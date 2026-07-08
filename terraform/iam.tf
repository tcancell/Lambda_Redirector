data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid     = "AllowLambdaAndEdgeAssumeRole"
    actions = ["sts:AssumeRole"]

    principals {
      type = "Service"
      identifiers = [
        "lambda.amazonaws.com",
        "edgelambda.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role" "lambda_edge" {
  provider = aws.us_east_1

  name               = "${local.resource_prefix}-lambda-edge-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "lambda_edge" {
  statement {
    sid = "WriteCloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:logs:*:${data.aws_caller_identity.current.account_id}:*",
    ]
  }

  statement {
    sid = "ReadRedirectConfigObject"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = [
      "${aws_s3_bucket.config.arn}/${var.config_key}",
    ]
  }

  statement {
    sid = "ListRedirectConfigPrefix"
    actions = [
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.config.arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = [var.config_key]
    }
  }

  statement {
    sid = "DecryptRedirectConfigObject"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [
      aws_kms_key.regional.arn,
    ]
  }
}

resource "aws_iam_role_policy" "lambda_edge" {
  provider = aws.us_east_1

  name   = "${local.resource_prefix}-lambda-edge-policy"
  role   = aws_iam_role.lambda_edge.id
  policy = data.aws_iam_policy_document.lambda_edge.json
}


data "aws_iam_policy_document" "config_compiler_assume_role" {
  statement {
    sid     = "AllowLambdaAssumeRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "config_compiler" {
  name               = "${local.resource_prefix}-config-compiler-role"
  assume_role_policy = data.aws_iam_policy_document.config_compiler_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "config_compiler" {
  statement {
    sid = "WriteCloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:logs:*:${data.aws_caller_identity.current.account_id}:*",
    ]
  }

  statement {
    sid = "ReadRedirectConfigObject"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = [
      "${aws_s3_bucket.config.arn}/${var.config_key}",
    ]
  }

  statement {
    sid = "UpdateCloudFrontKeyValueStore"
    actions = [
      "cloudfront-keyvaluestore:DescribeKeyValueStore",
      "cloudfront-keyvaluestore:ListKeys",
      "cloudfront-keyvaluestore:UpdateKeys",
    ]
    resources = [
      aws_cloudfront_key_value_store.redirect_fastpath.arn,
    ]
  }

  statement {
    sid = "UseRegionalKmsKey"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey*",
    ]
    resources = [
      aws_kms_key.regional.arn,
    ]
  }

  statement {
    sid = "WriteCompilerDeadLetterQueue"
    actions = [
      "sqs:SendMessage",
    ]
    resources = [
      aws_sqs_queue.config_compiler_dlq.arn,
    ]
  }

  statement {
    sid = "WriteXRayTraces"
    actions = [
      "xray:PutTelemetryRecords",
      "xray:PutTraceSegments",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "config_compiler" {
  name   = "${local.resource_prefix}-config-compiler-policy"
  role   = aws_iam_role.config_compiler.id
  policy = data.aws_iam_policy_document.config_compiler.json
}
