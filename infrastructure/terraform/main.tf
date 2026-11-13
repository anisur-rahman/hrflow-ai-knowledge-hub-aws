terraform {
  required_version = ">= 1.10"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.90" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Partial config: pass bucket/key/region with -backend-config (see README).
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = var.project, Environment = var.environment, ManagedBy = "terraform" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  name       = "${var.project}-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id
  azs        = slice(data.aws_availability_zones.available.names, 0, 2)
  app_url    = aws_apigatewayv2_api.this.api_endpoint
  db_secret  = aws_db_instance.this.master_user_secret[0].secret_arn
  images = {
    api    = "${aws_ecr_repository.this["api"].repository_url}:${var.image_tag}"
    web    = "${aws_ecr_repository.this["web"].repository_url}:${var.image_tag}"
    worker = "${aws_ecr_repository.this["worker"].repository_url}:${var.image_tag}"
  }
  # Settings shared by the API (ECS) and the ingestion worker (Lambda); see backend/app/config.py.
  app_env = {
    ENVIRONMENT             = var.environment
    LOG_LEVEL               = "INFO"
    AWS_REGION              = var.aws_region
    DB_HOST                 = aws_db_instance.this.address
    DB_PORT                 = tostring(aws_db_instance.this.port)
    DB_NAME                 = aws_db_instance.this.db_name
    DB_USER                 = aws_db_instance.this.username
    AI_PROVIDER             = "bedrock"
    BEDROCK_CHAT_MODEL_ID   = var.bedrock_chat_model_id
    BEDROCK_EMBED_MODEL_ID  = var.bedrock_embed_model_id
    BEDROCK_EFFORT          = var.bedrock_effort
    STORAGE_PROVIDER        = "s3"
    DOCUMENT_BUCKET         = aws_s3_bucket.documents.bucket
    INGESTION_QUEUE_URL     = aws_sqs_queue.ingest.url
    OCR_PROVIDER            = "textract"
    TEXTRACT_SNS_TOPIC_ARN  = aws_sns_topic.textract.arn
    TEXTRACT_ROLE_ARN       = aws_iam_role.textract.arn
    AUTH_MODE               = "cognito"
    COGNITO_USER_POOL_ID    = aws_cognito_user_pool.this.id
    COGNITO_CLIENT_ID       = aws_cognito_user_pool_client.web.id
    COGNITO_DOMAIN          = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com"
    ADMIN_GROUP             = "hr-admin"
    KNOWN_GROUPS            = join(",", var.user_groups)
    DEFAULT_DOCUMENT_GROUPS = "employee"
    CORS_ORIGINS            = local.app_url
  }
}

# ---------- ECR (api, web, worker images) ----------
resource "aws_ecr_repository" "this" {
  for_each             = toset(["api", "web", "worker"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = !var.deletion_protection
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_ecr_repository_policy" "worker_lambda" {
  repository = aws_ecr_repository.this["worker"].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LambdaPull"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      Condition = { StringLike = { "aws:sourceArn" = "arn:${data.aws_partition.current.partition}:lambda:${var.aws_region}:${local.account_id}:function:*" } }
    }]
  })
}
