data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  # Cross-region inference profiles route to foundation models in other regions, hence the region wildcard.
  bedrock_resources = [
    "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/*",
    "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}:${local.account_id}:inference-profile/*",
  ]
}

# ---------- ECS task execution (pull images, write logs, read the DB secret) ----------
resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secret" {
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [local.db_secret] }]
  })
}

# ---------- API task role ----------
resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy" "api" {
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DocumentObjects" # presigned POST (put), presigned GET for citations, delete
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.documents.arn}/uploads/*"]
      },
      { Sid = "Reprocess", Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [aws_sqs_queue.ingest.arn] },
      { Sid = "Bedrock", Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = local.bedrock_resources },
    ]
  })
}

# ---------- Web task role (no AWS access needed) ----------
resource "aws_iam_role" "web" {
  name               = "${local.name}-web"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

# ---------- Textract service role: publishes job completion to the SNS topic ----------
data "aws_iam_policy_document" "textract_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["textract.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "textract" {
  name               = "${local.name}-textract-sns"
  assume_role_policy = data.aws_iam_policy_document.textract_assume.json
}

resource "aws_iam_role_policy" "textract" {
  role = aws_iam_role.textract.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["sns:Publish"], Resource = [aws_sns_topic.textract.arn] }]
  })
}

# ---------- Lambda workers (ingest + textract callback share one role) ----------
resource "aws_iam_role" "worker" {
  name               = "${local.name}-worker"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "worker_vpc" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "worker" {
  role = aws_iam_role.worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "ReadDocuments", Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${aws_s3_bucket.documents.arn}/uploads/*"] },
      {
        Sid      = "Queue"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
        Resource = [aws_sqs_queue.ingest.arn, aws_sqs_queue.textract_results.arn]
      },
      # Textract async APIs do not support resource-level permissions.
      { Sid = "Ocr", Effect = "Allow", Action = ["textract:StartDocumentTextDetection", "textract:GetDocumentTextDetection"], Resource = ["*"] },
      { Sid = "TextractNotifications", Effect = "Allow", Action = ["iam:PassRole"], Resource = [aws_iam_role.textract.arn] },
      { Sid = "Bedrock", Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = local.bedrock_resources },
      { Sid = "DbSecret", Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [local.db_secret] },
    ]
  })
}
