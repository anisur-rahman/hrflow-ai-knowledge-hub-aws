# ---------- Ingest queue (S3 events, reprocess requests) + DLQ ----------
resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "${local.name}-ingest-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "ingest" {
  name                       = "${local.name}-ingest"
  visibility_timeout_seconds = 3600 # 6x the Lambda timeout, as AWS recommends
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingest_dlq.arn
    maxReceiveCount     = 3
  })
}

data "aws_iam_policy_document" "ingest_queue" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.documents.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "ingest" {
  queue_url = aws_sqs_queue.ingest.id
  policy    = data.aws_iam_policy_document.ingest_queue.json
}


# ---------- Textract completion: Textract -> SNS -> SQS (+ DLQ) -> textract_callback ----------
resource "aws_sns_topic" "textract" {
  name = "${local.name}-textract-results"
}

resource "aws_sqs_queue" "textract_dlq" {
  name                      = "${local.name}-textract-results-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "textract_results" {
  name                       = "${local.name}-textract-results"
  visibility_timeout_seconds = 3600
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.textract_dlq.arn
    maxReceiveCount     = 3
  })
}

data "aws_iam_policy_document" "textract_results_queue" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.textract_results.arn]
    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.textract.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "textract_results" {
  queue_url = aws_sqs_queue.textract_results.id
  policy    = data.aws_iam_policy_document.textract_results_queue.json
}

resource "aws_sns_topic_subscription" "textract_results" {
  topic_arn            = aws_sns_topic.textract.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.textract_results.arn
  raw_message_delivery = true
}

# ---------- Lambda workers (one image, two handlers) ----------
locals {
  workers = {
    ingest = {
      command = "workers.ingest_lambda.handler.handler"
      queue   = aws_sqs_queue.ingest.arn
    }
    textract-callback = {
      command = "workers.textract_callback.handler.handler"
      queue   = aws_sqs_queue.textract_results.arn
    }
  }
  # AWS_REGION is reserved (Lambda sets it); the DB password is read from Secrets Manager at cold start.
  worker_env = merge({ for k, v in local.app_env : k => v if k != "AWS_REGION" }, { DB_SECRET_ARN = local.db_secret })
}

resource "aws_cloudwatch_log_group" "worker" {
  for_each          = local.workers
  name              = "/aws/lambda/${local.name}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "worker" {
  for_each      = local.workers
  function_name = "${local.name}-${each.key}"
  package_type  = "Image"
  image_uri     = local.images.worker
  role          = aws_iam_role.worker.arn
  architectures = ["x86_64"]
  timeout       = 600 # extraction, Bedrock calls and embeddings; OCR waits happen in Textract, not here
  memory_size   = 2048
  image_config { command = [each.value.command] }
  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.worker.id]
  }
  environment { variables = local.worker_env }
  depends_on = [aws_cloudwatch_log_group.worker, aws_iam_role_policy_attachment.worker_vpc, aws_iam_role_policy.worker]
}

resource "aws_lambda_event_source_mapping" "worker" {
  for_each                = local.workers
  event_source_arn        = each.value.queue
  function_name           = aws_lambda_function.worker[each.key].arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config { maximum_concurrency = var.worker_max_concurrency }
}
