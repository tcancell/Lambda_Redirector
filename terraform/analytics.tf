resource "aws_cloudwatch_log_delivery_source" "redirect_access_logs" {
  provider = aws.us_east_1
  count    = var.enable_redirect_analytics ? 1 : 0

  name         = "${local.resource_prefix}-redirect-access-logs"
  log_type     = "ACCESS_LOGS"
  resource_arn = aws_cloudfront_distribution.redirect.arn
  tags         = local.common_tags
}

resource "aws_cloudwatch_log_delivery_destination" "redirect_access_logs" {
  provider = aws.us_east_1
  count    = var.enable_redirect_analytics ? 1 : 0

  name          = "${local.resource_prefix}-redirect-access-logs-s3"
  output_format = "parquet"
  tags          = local.common_tags

  delivery_destination_configuration {
    destination_resource_arn = "${aws_s3_bucket.logs.arn}/${local.cloudfront_v2_log_prefix}"
  }

  depends_on = [aws_s3_bucket_policy.logs]
}

resource "aws_cloudwatch_log_delivery" "redirect_access_logs" {
  provider = aws.us_east_1
  count    = var.enable_redirect_analytics ? 1 : 0

  delivery_source_name     = aws_cloudwatch_log_delivery_source.redirect_access_logs[0].name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.redirect_access_logs[0].arn
  record_fields            = local.cloudfront_v2_log_fields
  field_delimiter          = ""
  s3_delivery_configuration = [{
    enable_hive_compatible_path = true
    suffix_path                 = "{distributionid}/{yyyy}/{MM}/{dd}/{HH}"
  }]
}

resource "aws_glue_catalog_database" "redirect_analytics" {
  count = var.enable_redirect_analytics ? 1 : 0

  name        = local.analytics_database_name
  description = "CloudFront redirect access logs and request analytics."
  tags        = local.common_tags
}

resource "aws_glue_catalog_table" "redirect_access_logs" {
  count = var.enable_redirect_analytics ? 1 : 0

  name          = "cloudfront_redirect_requests"
  database_name = aws_glue_catalog_database.redirect_analytics[0].name
  description   = "CloudFront standard logging v2 access records for the redirect platform."
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                           = "TRUE"
    "projection.enabled"               = "true"
    "projection.distributionid.type"   = "enum"
    "projection.distributionid.values" = aws_cloudfront_distribution.redirect.id
    "projection.year.type"             = "integer"
    "projection.year.range"            = "2024,2035"
    "projection.month.type"            = "integer"
    "projection.month.range"           = "01,12"
    "projection.month.digits"          = "2"
    "projection.day.type"              = "integer"
    "projection.day.range"             = "01,31"
    "projection.day.digits"            = "2"
    "projection.hour.type"             = "integer"
    "projection.hour.range"            = "00,23"
    "projection.hour.digits"           = "2"
    "storage.location.template"        = "s3://${aws_s3_bucket.logs.bucket}/${local.cloudfront_v2_log_prefix}/distributionid=$${distributionid}/year=$${year}/month=$${month}/day=$${day}/hour=$${hour}/"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.logs.bucket}/${local.cloudfront_v2_log_prefix}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "date"
      type = "string"
    }

    columns {
      name = "time"
      type = "string"
    }

    columns {
      name = "x_edge_location"
      type = "string"
    }

    columns {
      name = "c_ip"
      type = "string"
    }

    columns {
      name = "cs_method"
      type = "string"
    }

    columns {
      name = "cs_host"
      type = "string"
    }

    columns {
      name = "cs_uri_stem"
      type = "string"
    }

    columns {
      name = "sc_status"
      type = "string"
    }

    columns {
      name = "cs_uri_query"
      type = "string"
    }

    columns {
      name = "x_edge_result_type"
      type = "string"
    }

    columns {
      name = "x_edge_request_id"
      type = "string"
    }

    columns {
      name = "x_host_header"
      type = "string"
    }

    columns {
      name = "cs_protocol"
      type = "string"
    }

    columns {
      name = "time_taken"
      type = "string"
    }

    columns {
      name = "x_edge_detailed_result_type"
      type = "string"
    }
  }

  partition_keys {
    name = "distributionid"
    type = "string"
  }

  partition_keys {
    name = "year"
    type = "int"
  }

  partition_keys {
    name = "month"
    type = "int"
  }

  partition_keys {
    name = "day"
    type = "int"
  }

  partition_keys {
    name = "hour"
    type = "int"
  }
}

resource "aws_athena_workgroup" "redirect_analytics" {
  count = var.enable_redirect_analytics ? 1 : 0

  name        = local.analytics_workgroup_name
  description = "Cost-controlled Athena queries for CloudFront redirect request tracking."
  state       = "ENABLED"
  tags        = local.common_tags

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.analytics_query_bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${aws_s3_bucket.logs.bucket}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

resource "aws_athena_named_query" "redirect_request_details" {
  count = var.enable_redirect_analytics ? 1 : 0

  name        = "Redirect request details (last 30 days)"
  description = "Recent redirect requests including timestamp, requested URL, viewer IP, status, and CloudFront request ID."
  database    = aws_glue_catalog_database.redirect_analytics[0].name
  workgroup   = aws_athena_workgroup.redirect_analytics[0].name
  query       = <<-SQL
    SELECT
      date_parse(concat(date, ' ', time), '%Y-%m-%d %H:%i:%s') AS requested_at_utc,
      c_ip AS viewer_ip,
      concat(
        coalesce(nullif(cs_protocol, '-'), 'https'),
        '://',
        coalesce(nullif(x_host_header, '-'), cs_host),
        cs_uri_stem,
        if(cs_uri_query IS NULL OR cs_uri_query = '-', '', concat('?', cs_uri_query))
      ) AS requested_url,
      cs_method,
      sc_status,
      x_edge_result_type,
      x_edge_detailed_result_type,
      x_edge_request_id
    FROM cloudfront_redirect_requests
    WHERE date >= date_format(current_date - interval '30' day, '%Y-%m-%d')
      AND year BETWEEN year(current_date - interval '30' day) AND year(current_date)
      AND sc_status IN ('301', '302', '307', '308')
    ORDER BY requested_at_utc DESC
    LIMIT 1000
  SQL
}

resource "aws_athena_named_query" "redirect_url_totals" {
  count = var.enable_redirect_analytics ? 1 : 0

  name        = "Redirect URL totals (last 30 days)"
  description = "Total requests and redirect responses for each requested URL during the last 30 days."
  database    = aws_glue_catalog_database.redirect_analytics[0].name
  workgroup   = aws_athena_workgroup.redirect_analytics[0].name
  query       = <<-SQL
    SELECT
      concat(
        coalesce(nullif(cs_protocol, '-'), 'https'),
        '://',
        coalesce(nullif(x_host_header, '-'), cs_host),
        cs_uri_stem,
        if(cs_uri_query IS NULL OR cs_uri_query = '-', '', concat('?', cs_uri_query))
      ) AS requested_url,
      count(*) AS request_count,
      sum(CASE WHEN sc_status IN ('301', '302', '307', '308') THEN 1 ELSE 0 END) AS redirect_count,
      min(date_parse(concat(date, ' ', time), '%Y-%m-%d %H:%i:%s')) AS first_requested_at_utc,
      max(date_parse(concat(date, ' ', time), '%Y-%m-%d %H:%i:%s')) AS last_requested_at_utc
    FROM cloudfront_redirect_requests
    WHERE date >= date_format(current_date - interval '30' day, '%Y-%m-%d')
      AND year BETWEEN year(current_date - interval '30' day) AND year(current_date)
    GROUP BY 1
    ORDER BY request_count DESC, requested_url
  SQL
}
