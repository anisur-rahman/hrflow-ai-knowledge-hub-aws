# AWS infrastructure (Terraform)

| File | Contents |
|---|---|
| `bootstrap/` | One-time: Terraform state bucket, GitHub OIDC provider, deploy role |
| `main.tf` | Providers, shared settings passed to the API and workers, ECR repositories |
| `networking.tf` | VPC, 2 AZs, private subnets, single NAT gateway, S3 gateway endpoint, security groups |
| `s3.tf` | Private, versioned, encrypted document bucket; upload events → SQS |
| `rds.tf` | RDS PostgreSQL 17 (pgvector), password in Secrets Manager |
| `ecs.tf` | Internal ALB, ECS Fargate `api` + `web` services with CPU auto scaling |
| `lambda.tf` | Ingest queue + DLQ; Textract → SNS → results queue + DLQ; `ingest` and `textract-callback` Lambdas |
| `iam.tf` | Least-privilege roles for the ECS tasks, the workers and Textract's SNS publishing |
| `api_gateway.tf` | HTTP API, VPC link, Cognito JWT authorizer, throttling, access logs |
| `cognito.tf` | User pool, hosted UI domain, SPA client (code + PKCE), groups |
| `monitoring.tf` | Log metric filters, alarms → SNS, CloudWatch dashboard |

See the root README, section "Deploy to AWS", for the deployment steps. Validate without AWS credentials:

```bash
terraform init -backend=false && terraform validate
```
