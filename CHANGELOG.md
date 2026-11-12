# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-12

First release.

### Added

**Document management (HR)**
- Two-step PDF upload: the API creates the record and returns a presigned S3 POST, so files go straight from the browser to a private bucket (local mode stores them in a Docker volume).
- Background ingestion: PyMuPDF text extraction with section-heading detection, Bedrock categorization and summarization, page-aware overlapping chunks, and Titan Text Embeddings V2 vectors in PostgreSQL + pgvector (HNSW index).
- Asynchronous Textract OCR for scanned PDFs: Textract → SNS → SQS → `textract_callback` Lambda, so no function waits for OCR.
- Review workflow: AI proposals stay in *Needs review* until HR approves (editing category, summary, version and visible groups) or rejects them. Only published documents are ever used for answers.
- Reprocess, delete, document versions, and per-document visibility by user group.
- HR dashboard: review queue, failed and in-progress documents, question counts, unanswered questions and recent activity.
- Audit trail of uploads, reviews, deletions, opened sources and questions.

**Policy assistant (employees)**
- Retrieval-augmented answers from Amazon Bedrock using only published documents the user is allowed to see, filtered in SQL before any text reaches the model.
- Citations with document title, version, page and section; each opens the source PDF at the cited page through a short-lived link.
- Follow-up questions with conversation history; the model is never called without evidence.

**Platform**
- Vue 3 + TypeScript + PrimeVue frontend with routing, an HR-only dashboard, and Cognito sign-in (authorization code + PKCE).
- FastAPI backend split into `api/`, `services/`, `models/`, `schemas/` and `security/`, with Alembic migrations protected by an advisory lock.
- Lambda workers (`ingest_lambda`, `textract_callback`) sharing the backend services, with SQS partial batch failures and dead-letter queues.
- Structured JSON logging with request IDs, turned into CloudWatch metrics, alarms and a dashboard.
- Local mode that runs offline with Docker Compose, mock AI, and a one-click **Use demo key** sign-in.

**Infrastructure and delivery**
- Terraform for AWS: VPC, API Gateway (HTTP API + VPC link + JWT authorizer), internal ALB, ECS Fargate, RDS PostgreSQL 17, S3, SQS, SNS, Lambda, Cognito, ECR, IAM and CloudWatch, plus a bootstrap stack for Terraform state and the GitHub OIDC deploy role.
- GitHub Actions: CI (Ruff, pytest against pgvector, frontend type check and build, `npm audit`, `terraform validate`, image builds) and a gated **Deploy to AWS** workflow with smoke tests.
- Test suite covering documents, RAG, security (including Cognito token verification) and ingestion, including the asynchronous OCR flow.

**Documentation and community**
- README with badges, screenshots, architecture, annotated project structure and API reference.
- Step-by-step guides: [getting started](docs/GETTING_STARTED.md) (local, development, deployment with GitHub Actions) and [command-line deployment](docs/DEPLOY_AWS_CLI.md).
- MIT license, contributing guide, Contributor Covenant code of conduct, security policy, issue forms and a pull request template.

### Fixed
- `terraform destroy` could not remove the versioned documents bucket once files had been uploaded.

[Unreleased]: https://github.com/anisur-rahman/hrflow-ai-knowledge-hub-aws/commits/main
[1.0.0]: https://github.com/anisur-rahman/hrflow-ai-knowledge-hub-aws/commits/main
