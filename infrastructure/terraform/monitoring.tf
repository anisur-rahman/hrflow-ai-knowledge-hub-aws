locals {
  metric_namespace = "HRFlow/${var.environment}"
  # Structured application logs -> custom metrics (see backend/app/observability.py).
  worker_metrics = {
    IngestionSucceeded  = { value = "1", pattern = "{ $.event = \"ingestion.completed\" && $.outcome = \"succeeded\" }" }
    IngestionFailed     = { value = "1", pattern = "{ $.event = \"ingestion.completed\" && ($.outcome = \"failed\" || $.outcome = \"error\") }" }
    IngestionDuration   = { value = "$.duration_ms", pattern = "{ $.event = \"ingestion.completed\" && $.outcome = \"succeeded\" }" }
    OcrJobsStarted      = { value = "1", pattern = "{ $.event = \"ingestion.ocr_started\" }" }
    BedrockInputTokens  = { value = "$.input_tokens", pattern = "{ $.event = \"bedrock.converse\" }" }
    BedrockOutputTokens = { value = "$.output_tokens", pattern = "{ $.event = \"bedrock.converse\" }" }
  }
  api_metrics = {
    ChatLatency         = { value = "$.duration_ms", pattern = "{ $.event = \"chat.answered\" }" }
    ChatNoEvidence      = { value = "1", pattern = "{ $.event = \"chat.answered\" && $.source_count = 0 }" }
    ApiServerErrors     = { value = "1", pattern = "{ $.event = \"http.request\" && $.status >= 500 }" }
    BedrockInputTokens  = { value = "$.input_tokens", pattern = "{ $.event = \"bedrock.converse\" }" }
    BedrockOutputTokens = { value = "$.output_tokens", pattern = "{ $.event = \"bedrock.converse\" }" }
    BedrockLatency      = { value = "$.duration_ms", pattern = "{ $.event = \"bedrock.converse\" }" }
  }
  # Same metric name from several log groups adds up in CloudWatch.
  metric_filters = merge(
    { for pair in setproduct(keys(local.workers), keys(local.worker_metrics)) : "${pair[0]}-${pair[1]}" => merge(
    local.worker_metrics[pair[1]], { metric = pair[1], log_group = aws_cloudwatch_log_group.worker[pair[0]].name }) },
    { for name, m in local.api_metrics : "api-${name}" => merge(m, { metric = name, log_group = aws_cloudwatch_log_group.api.name }) },
  )
}

resource "aws_cloudwatch_log_metric_filter" "app" {
  for_each       = local.metric_filters
  name           = each.key
  log_group_name = each.value.log_group
  pattern        = each.value.pattern
  metric_transformation {
    name      = each.value.metric
    namespace = local.metric_namespace
    value     = each.value.value
  }
}

resource "aws_sns_topic" "alarms" {
  name = "${local.name}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarms = {
    "ingest-dlq-not-empty" = {
      description = "Documents failed ingestion 3 times and are in the DLQ. Inspect worker logs, fix, then Reprocess."
      namespace   = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", stat = "Maximum", threshold = 0
      dimensions  = { QueueName = aws_sqs_queue.ingest_dlq.name }
    }
    "textract-dlq-not-empty" = {
      description = "OCR completions failed 3 times. Inspect textract-callback logs; affected documents stay in ocr_pending until reprocessed."
      namespace   = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", stat = "Maximum", threshold = 0
      dimensions  = { QueueName = aws_sqs_queue.textract_dlq.name }
    }
    "ingestion-failures" = {
      description = "Document ingestion failures (bad PDFs or transient errors)."
      namespace   = local.metric_namespace, metric = "IngestionFailed", stat = "Sum", threshold = 0, dimensions = {}
    }
    "ingest-worker-errors" = {
      description = "Ingest Lambda invocation errors."
      namespace   = "AWS/Lambda", metric = "Errors", stat = "Sum", threshold = 0
      dimensions  = { FunctionName = aws_lambda_function.worker["ingest"].function_name }
    }
    "textract-callback-errors" = {
      description = "Textract callback Lambda invocation errors."
      namespace   = "AWS/Lambda", metric = "Errors", stat = "Sum", threshold = 0
      dimensions  = { FunctionName = aws_lambda_function.worker["textract-callback"].function_name }
    }
    "api-5xx" = {
      description = "API Gateway 5xx responses."
      namespace   = "AWS/ApiGateway", metric = "5xx", stat = "Sum", threshold = 5
      dimensions  = { ApiId = aws_apigatewayv2_api.this.id, Stage = "$default" }
    }
    "api-unhealthy-targets" = {
      description = "API tasks failing ALB health checks."
      namespace   = "AWS/ApplicationELB", metric = "UnHealthyHostCount", stat = "Maximum", threshold = 0
      dimensions  = { LoadBalancer = aws_lb.this.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix }
    }
    "api-cpu-high" = {
      description = "API service CPU above 80% (auto scaling may be at its maximum)."
      namespace   = "AWS/ECS", metric = "CPUUtilization", stat = "Average", threshold = 80
      dimensions  = { ClusterName = aws_ecs_cluster.this.name, ServiceName = aws_ecs_service.api.name }
    }
    "db-cpu-high" = {
      description = "RDS CPU above 80%."
      namespace   = "AWS/RDS", metric = "CPUUtilization", stat = "Average", threshold = 80
      dimensions  = { DBInstanceIdentifier = aws_db_instance.this.identifier }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each            = local.alarms
  alarm_name          = "${local.name}-${each.key}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  statistic           = each.value.stat
  dimensions          = each.value.dimensions
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = each.value.threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "db_storage_low" {
  alarm_name          = "${local.name}-db-storage-low"
  alarm_description   = "RDS free storage below 2 GiB."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.this.identifier }
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 2147483648
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = local.name
  dashboard_body = jsonencode({
    widgets = [
      for i, w in [
        { title = "Ingestion outcomes", metrics = [[local.metric_namespace, "IngestionSucceeded"], [local.metric_namespace, "IngestionFailed"]], stat = "Sum" },
        { title = "Ingestion duration (ms)", metrics = [[local.metric_namespace, "IngestionDuration"]], stat = "p90" },
        { title = "Queues and DLQs (visible messages)", metrics = [for q in [aws_sqs_queue.ingest, aws_sqs_queue.ingest_dlq, aws_sqs_queue.textract_results, aws_sqs_queue.textract_dlq] : ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", q.name]], stat = "Maximum" },
        { title = "OCR jobs started", metrics = [[local.metric_namespace, "OcrJobsStarted"]], stat = "Sum" },
        { title = "Chat latency (ms)", metrics = [[local.metric_namespace, "ChatLatency"]], stat = "p90" },
        { title = "Questions without evidence", metrics = [[local.metric_namespace, "ChatNoEvidence"]], stat = "Sum" },
        { title = "Bedrock tokens", metrics = [[local.metric_namespace, "BedrockInputTokens"], [local.metric_namespace, "BedrockOutputTokens"]], stat = "Sum" },
        { title = "API Gateway requests / 5xx", metrics = [["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.this.id, "Stage", "$default"], ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.this.id, "Stage", "$default"]], stat = "Sum" },
        { title = "API CPU / memory (%)", metrics = [["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.this.name, "ServiceName", "api"], ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.this.name, "ServiceName", "api"]], stat = "Average" },
        { title = "RDS CPU (%)", metrics = [["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.this.identifier]], stat = "Average" },
        ] : {
        type       = "metric"
        x          = (i % 3) * 8
        y          = floor(i / 3) * 6
        width      = 8
        height     = 6
        properties = { title = w.title, metrics = w.metrics, stat = w.stat, period = 300, region = var.aws_region, view = "timeSeries" }
      }
    ]
  })
}
