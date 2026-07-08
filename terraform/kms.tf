data "aws_iam_policy_document" "regional_kms" {
  statement {
    sid = "AllowAccountKeyAdministration"

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid = "AllowCloudWatchLogsUse"

    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.region}.amazonaws.com"]
    }

    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]

    resources = ["*"]
  }

  statement {
    sid = "AllowCloudFrontReadFallbackOrigin"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_kms_key" "regional" {
  description             = "KMS key for Lambda Redirect regional logs and S3 buckets"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.regional_kms.json
  tags                    = local.common_tags
}

resource "aws_kms_alias" "regional" {
  name          = "alias/${local.resource_prefix}-regional"
  target_key_id = aws_kms_key.regional.key_id
}

data "aws_iam_policy_document" "us_east_1_kms" {
  provider = aws.us_east_1

  statement {
    sid = "AllowAccountKeyAdministration"

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid = "AllowCloudWatchLogsUse"

    principals {
      type        = "Service"
      identifiers = ["logs.us-east-1.amazonaws.com"]
    }

    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]

    resources = ["*"]
  }
}

resource "aws_kms_key" "us_east_1" {
  provider = aws.us_east_1

  description             = "KMS key for Lambda Redirect us-east-1 logs"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.us_east_1_kms.json
  tags                    = local.common_tags
}

resource "aws_kms_alias" "us_east_1" {
  provider = aws.us_east_1

  name          = "alias/${local.resource_prefix}-us-east-1"
  target_key_id = aws_kms_key.us_east_1.key_id
}
