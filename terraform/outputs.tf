output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID."
  value       = aws_cloudfront_distribution.redirect.id
}

output "cloudfront_distribution_domain" {
  description = "CloudFront distribution domain name."
  value       = aws_cloudfront_distribution.redirect.domain_name
}

output "config_bucket_name" {
  description = "S3 bucket that stores the redirect configuration file."
  value       = aws_s3_bucket.config.bucket
}

output "config_object_key" {
  description = "S3 key for the redirect configuration file."
  value       = var.config_key
}

output "lambda_function_arn" {
  description = "Unqualified Lambda function ARN."
  value       = aws_lambda_function.redirect_engine.arn
}

output "lambda_edge_qualified_arn" {
  description = "Published Lambda@Edge version ARN attached to CloudFront."
  value       = aws_lambda_function.redirect_engine.qualified_arn
}

output "route53_record_names" {
  description = "Route 53 alias records created by this module."
  value       = keys(var.route53_zone_ids)
}

output "lambda_execution_role_name" {
  description = "IAM execution role name used by the Lambda@Edge function."
  value       = aws_iam_role.lambda_edge.name
}


output "fastpath_key_value_store_arn" {
  description = "CloudFront KeyValueStore ARN used by the fast-path CloudFront Function."
  value       = aws_cloudfront_key_value_store.redirect_fastpath.arn
}

output "config_compiler_lambda_name" {
  description = "S3-triggered Lambda function that compiles redirect config into CloudFront KeyValueStore."
  value       = aws_lambda_function.config_compiler.function_name
}
