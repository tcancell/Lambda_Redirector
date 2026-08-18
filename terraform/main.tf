terraform {
  required_version = ">= 1.5.0"

  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  environment_slug = trim(replace(lower(var.environment_name), "/[^a-z0-9-]/", "-"), "-")
  resource_prefix  = substr("redirect-${local.environment_slug}", 0, 40)


  config_bucket_name = var.config_bucket_name != "" ? var.config_bucket_name : substr(
    lower("${local.resource_prefix}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.region}-config"),
    0,
    63,
  )

  fallback_bucket_name = var.fallback_bucket_name != "" ? var.fallback_bucket_name : substr(
    lower("${local.resource_prefix}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.region}-fallback"),
    0,
    63,
  )

  lambda_function_name = substr("${local.resource_prefix}-redirect-edge", 0, 64)
  fallback_origin_id   = "${local.resource_prefix}-fallback-s3"

  analytics_database_name  = substr(replace("${local.resource_prefix}_analytics", "-", "_"), 0, 252)
  analytics_workgroup_name = substr("${local.resource_prefix}-redirect-analytics", 0, 128)

  cloudfront_v2_log_prefix = "cloudfront-v2"
  cloudfront_v2_log_fields = [
    "date",
    "time",
    "x-edge-location",
    "c-ip",
    "cs-method",
    "cs(Host)",
    "cs-uri-stem",
    "sc-status",
    "cs-uri-query",
    "x-edge-result-type",
    "x-edge-request-id",
    "x-host-header",
    "cs-protocol",
    "time-taken",
    "x-edge-detailed-result-type",
  ]

  allowed_redirect_hosts_csv = join(",", var.allowed_redirect_hosts)

  common_tags = merge(
    var.tags,
    {
      Application = "aws-url-redirect-platform"
      Environment = var.environment_name
      ManagedBy   = "terraform"
    }
  )
}
