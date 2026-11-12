output "app_url" {
  description = "Open this in a browser (API Gateway endpoint serving the Vue app and /api)."
  value       = local.app_url
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "cognito_hosted_ui" {
  value = local.app_env.COGNITO_DOMAIN
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "document_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "dead_letter_queues" {
  value = { ingest = aws_sqs_queue.ingest_dlq.url, textract_results = aws_sqs_queue.textract_dlq.url }
}

output "dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards/dashboard/${aws_cloudwatch_dashboard.this.dashboard_name}"
}

output "create_admin_user" {
  description = "Example: create an HR admin (Cognito emails a temporary password)."
  value       = <<-EOT
    aws cognito-idp admin-create-user --user-pool-id ${aws_cognito_user_pool.this.id} --username jane.hr \
      --user-attributes Name=email,Value=jane@example.com Name=email_verified,Value=true
    aws cognito-idp admin-add-user-to-group --user-pool-id ${aws_cognito_user_pool.this.id} --username jane.hr --group-name hr-admin
    aws cognito-idp admin-add-user-to-group --user-pool-id ${aws_cognito_user_pool.this.id} --username jane.hr --group-name employee
  EOT
}
