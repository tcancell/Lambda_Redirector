variable "aws_region" {
  description = "AWS region for regional resources such as S3. Lambda@Edge is always deployed in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "environment_name" {
  description = "Short environment name used in resource names and tags."
  type        = string
  default     = "dev"

  validation {
    condition     = length(trim(var.environment_name, " ")) > 0
    error_message = "environment_name must not be empty."
  }
}

variable "domains" {
  description = "Compatibility variable only. CloudFront alternate domain names are managed in the AWS Console and ignored by Terraform."
  type        = list(string)
  default     = []
}

variable "acm_certificate_arn" {
  description = "Compatibility variable only. CloudFront viewer certificates are managed in the AWS Console and ignored by Terraform."
  type        = string
  default     = ""
}

variable "config_bucket_name" {
  description = "Optional existing-style name for the S3 bucket that stores redirect configs. Leave empty to generate one."
  type        = string
  default     = ""
}

variable "fallback_bucket_name" {
  description = "Optional name for the private S3 fallback origin bucket. Leave empty to generate one."
  type        = string
  default     = ""
}

variable "config_key" {
  description = "S3 object key for the Apache-style redirect configuration file."
  type        = string
  default     = "redirects.conf"
}

variable "manage_sample_config_object" {
  description = "Upload examples/redirects.conf to S3 through Terraform. Disable if another pipeline owns the config object."
  type        = bool
  default     = true
}

variable "invoke_compiler_after_config_apply" {
  description = "Synchronously invoke the config compiler after Terraform writes examples/redirects.conf to S3. This reduces the window where first requests can fall back to Lambda@Edge before CloudFront KeyValueStore is updated."
  type        = bool
  default     = true
}

variable "force_destroy_buckets" {
  description = "Allow Terraform to delete non-empty buckets. Keep false for production unless you know you want cleanup behavior."
  type        = bool
  default     = false
}

variable "config_check_interval_seconds" {
  description = "How often each warm Lambda runtime checks S3 metadata for config changes."
  type        = number
  default     = 30
}

variable "redirect_cache_ttl_seconds" {
  description = "CloudFront cache TTL, in seconds, for Lambda@Edge fallback redirect responses. Keep 0 unless every fallback rule only depends on cache-key fields."
  type        = number
  default     = 0

  validation {
    condition     = var.redirect_cache_ttl_seconds >= 0
    error_message = "redirect_cache_ttl_seconds must be 0 or greater."
  }
}

variable "fastpath_redirect_cache_ttl_seconds" {
  description = "Cache-Control max-age, in seconds, returned by CloudFront Function fast-path redirects. This is a client/proxy hint; CloudFront Function still evaluates every viewer request."
  type        = number
  default     = 600

  validation {
    condition     = var.fastpath_redirect_cache_ttl_seconds >= 0
    error_message = "fastpath_redirect_cache_ttl_seconds must be 0 or greater."
  }
}

variable "allowed_redirect_hosts" {
  description = "Optional allowlist of absolute redirect destination hosts. Leave empty only for non-production or fully trusted redirect configs. Wildcards such as *.example.com are supported."
  type        = list(string)
  default     = []
}

variable "require_https_redirect_targets" {
  description = "Require absolute redirect targets to use HTTPS. Relative targets are still allowed."
  type        = bool
  default     = true
}

variable "max_redirect_config_bytes" {
  description = "Maximum size, in bytes, for the Apache-style redirect config object."
  type        = number
  default     = 262144
}

variable "enable_diagnostic_headers" {
  description = "Return x-redirect-engine response headers for troubleshooting. Keep false in production unless actively debugging."
  type        = bool
  default     = false
}

variable "fallback_behavior" {
  description = "Behavior when no rule matches. Use not_found to return from Lambda or pass_through to send the request to the fallback origin."
  type        = string
  default     = "not_found"

  validation {
    condition     = contains(["not_found", "pass_through"], var.fallback_behavior)
    error_message = "fallback_behavior must be either not_found or pass_through."
  }
}

variable "fallback_status_code" {
  description = "Status code returned by Lambda when fallback_behavior is not_found."
  type        = number
  default     = 404

  validation {
    condition     = contains([400, 403, 404, 410], var.fallback_status_code)
    error_message = "fallback_status_code must be one of 400, 403, 404, or 410."
  }
}

variable "fallback_body" {
  description = "Plain-text body returned when fallback_behavior is not_found."
  type        = string
  default     = "No redirect rule matched this request."
}

variable "lambda_runtime" {
  description = "Python runtime for the Lambda@Edge function."
  type        = string
  default     = "python3.12"
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 128
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds. A longer timeout reduces first-request failures while Lambda@Edge fetches config from S3 after idle periods."
  type        = number
  default     = 15
}

variable "compiler_lambda_memory_size" {
  description = "Memory size in MB for the S3-triggered config compiler Lambda."
  type        = number
  default     = 256
}

variable "compiler_lambda_timeout_seconds" {
  description = "Timeout in seconds for the S3-triggered config compiler Lambda."
  type        = number
  default     = 30
}

variable "compiler_reserved_concurrent_executions" {
  description = "Reserved concurrency for the config compiler Lambda."
  type        = number
  default     = 5
}

variable "lambda_code_signing_config_arn" {
  description = "Optional Lambda code signing config ARN. Lambda@Edge and compiler functions use it when provided."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "Retention for Lambda log groups. Keep at least 365 days for audit-ready production deployments."
  type        = number
  default     = 365
}

variable "access_log_retention_days" {
  description = "Retention period for S3, CloudFront, and Athena query-result logs."
  type        = number
  default     = 365
}

variable "enable_redirect_analytics" {
  description = "Enable CloudFront standard logging v2, the Athena catalog, and saved redirect-usage queries."
  type        = bool
  default     = true
}

variable "enable_legacy_cloudfront_access_logs" {
  description = "Continue delivering legacy CloudFront access logs while standard logging v2 is rolled out. Disable after verifying v2 delivery if duplicate raw logs are not needed."
  type        = bool
  default     = true
}

variable "analytics_query_bytes_scanned_cutoff" {
  description = "Maximum bytes Athena can scan per redirect-analytics query. This limits accidental query cost."
  type        = number
  default     = 10737418240

  validation {
    condition     = var.analytics_query_bytes_scanned_cutoff > 0
    error_message = "analytics_query_bytes_scanned_cutoff must be greater than zero."
  }
}

variable "config_noncurrent_version_retention_days" {
  description = "Retention period for noncurrent redirect config object versions."
  type        = number
  default     = 365
}

variable "alarm_actions" {
  description = "SNS topic ARNs or other CloudWatch alarm actions for production alerts."
  type        = list(string)
  default     = []
}

variable "ok_actions" {
  description = "SNS topic ARNs or other CloudWatch OK actions for production alerts."
  type        = list(string)
  default     = []
}

variable "viewer_protocol_policy" {
  description = "CloudFront viewer protocol policy."
  type        = string
  default     = "redirect-to-https"

  validation {
    condition     = contains(["allow-all", "https-only", "redirect-to-https"], var.viewer_protocol_policy)
    error_message = "viewer_protocol_policy must be allow-all, https-only, or redirect-to-https."
  }
}

variable "cloudfront_price_class" {
  description = "CloudFront price class."
  type        = string
  default     = "PriceClass_100"
}

variable "wait_for_cloudfront_deployment" {
  description = "Wait for CloudFront deployment to complete during terraform apply."
  type        = bool
  default     = true
}

variable "route53_zone_ids" {
  description = "Map of DNS record name to Route 53 hosted zone ID. Example: { \"example.com\" = \"Z123\" }"
  type        = map(string)
  default     = {}
}

variable "create_ipv6_route53_records" {
  description = "Create AAAA alias records in Route 53 in addition to A records."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags to apply to supported resources."
  type        = map(string)
  default     = {}
}
