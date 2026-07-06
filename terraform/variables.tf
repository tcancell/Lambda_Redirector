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
  description = "CloudFront cache TTL, in seconds, for Lambda-generated redirect responses. Set to 0 to disable redirect response caching."
  type        = number
  default     = 600

  validation {
    condition     = var.redirect_cache_ttl_seconds >= 0
    error_message = "redirect_cache_ttl_seconds must be 0 or greater."
  }
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

variable "log_retention_days" {
  description = "Retention for the primary Lambda log group in us-east-1."
  type        = number
  default     = 30
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
