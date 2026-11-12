variable "project" {
  type    = string
  default = "hrflow"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "image_tag" {
  description = "Container image tag (git SHA) for the api, web and worker images."
  type        = string
}

variable "bedrock_chat_model_id" {
  description = "Converse-compatible model or inference profile ID enabled in this account and region."
  type        = string
}

variable "bedrock_embed_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "deletion_protection" {
  description = "Protect the database from deletion. Set true for anything holding real data."
  type        = bool
  default     = false
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "api_max_count" {
  type    = number
  default = 4
}

variable "worker_max_concurrency" {
  description = "Maximum concurrent Lambda ingestion workers (protects RDS and Bedrock quotas)."
  type        = number
  default     = 5
}

variable "user_groups" {
  type    = list(string)
  default = ["employee", "hr-admin"]
}

variable "alarm_email" {
  description = "Optional email for CloudWatch alarm notifications."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  type    = number
  default = 30
}
