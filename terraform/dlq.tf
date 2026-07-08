resource "aws_sqs_queue" "config_compiler_dlq" {
  name                              = "${local.resource_prefix}-config-compiler-dlq"
  message_retention_seconds         = 1209600
  kms_master_key_id                 = aws_kms_key.regional.arn
  kms_data_key_reuse_period_seconds = 300
  tags                              = local.common_tags
}
