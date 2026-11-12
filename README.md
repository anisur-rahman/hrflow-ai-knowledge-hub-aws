# HRFlow AI Knowledge Hub

An AI-enabled HR & Operations knowledge hub. HR uploads policy PDFs, AI proposes a category and summary, HR reviews and publishes, and employees ask questions in plain language and get answers grounded in the published policies, with page citations that open the source PDF.

**Stack:** Vue 3 + TypeScript + PrimeVue · Python + FastAPI · PostgreSQL + pgvector · Amazon Bedrock (Titan Text Embeddings V2 + a Converse chat model) · S3 · SQS · Lambda · Textract · ECS Fargate · API Gateway · Cognito · RDS · CloudWatch · GitHub Actions + ECR · Terraform

## Architecture

```text
Document ingestion
  Vue ──► API Gateway ──► FastAPI (ECS) ── presigned POST ──► Vue uploads PDF straight to private S3
  S3 ObjectCreated ──► SQS (DLQ after 3 tries) ──► ingest_lambda
     ├─ PyMuPDF text + heading detection
     │    └─ scanned PDF? start async Textract and stop ──► Textract ──► SNS ──► SQS ──► textract_callback
     ├─ Bedrock: category + proposed summary
     ├─ page-aware overlapping chunks with section headings
     └─ Bedrock Titan embeddings ──► RDS PostgreSQL + pgvector ──► status "pending_review"
  HR reviews / edits ──► "published"  (only published documents are ever retrieved)

Employee question
  Vue ──► API Gateway (Cognito JWT check) ──► FastAPI
     ├─ verify token again, read Cognito groups
     ├─ Bedrock embedding of the question
     ├─ pgvector search, filtered in SQL to published documents shared with the user's groups
     └─ Bedrock Converse with only that evidence ──► answer + citations (title, version, page, section, PDF link)
```

| Concern | Implementation |
|---|---|
| Entry point | API Gateway HTTP API → VPC link → internal ALB → ECS Fargate (`api` and `web` services) |
| Auth | Cognito hosted UI (authorization code + PKCE). API Gateway JWT authorizer, and the API verifies the access token again. Groups: `hr-admin`, `employee` |
| Authorization | Each document has `allowed_groups`; retrieval filters by group in SQL *before* any text reaches the LLM |
| Review workflow | `awaiting_upload → queued → processing → pending_review → published / rejected`, or `failed` (with reason, retry, reprocess) |
| Ingestion | Same Python services locally (background task) and in two Lambdas: `ingest_lambda` and `textract_callback`. No Lambda waits on OCR. Idempotent (row lock + status checks + chunk replacement); SQS partial-batch failures + DLQs |
| Storage | Private, versioned, encrypted S3; TLS-only bucket policy; presigned POST capped at 10 MB; 5-minute presigned GET for citations |
| Database | RDS PostgreSQL 17 + pgvector HNSW index; password managed by Secrets Manager; Alembic migrations behind an advisory lock |
| Observability | JSON logs with request IDs → CloudWatch metric filters (ingestion outcomes, chat latency, questions with no evidence, Bedrock tokens) → alarms + dashboard |
| CI/CD | CI: ruff, pytest against real pgvector, type-checked build, `npm audit`, `terraform validate`, image builds. Deploy: GitHub OIDC → ECR → `terraform apply` → wait for ECS → smoke test |

## Repository layout

```text
frontend/                 Vue 3 + TypeScript + PrimeVue
  src/views/              DashboardView (HR), DocumentsView, ChatView, LoginView
  src/components/         DocumentUpload, DocumentList, ReviewDialog, AIChatbot
  src/services/           api.ts, auth.ts (Cognito OIDC / local key), session.ts, documents.ts
  src/router/             routes + HR-only guard
backend/
  app/main.py             FastAPI app, middleware, health and config
  app/api/                documents.py, chat.py, admin.py (review, reprocess, delete, stats, audit)
  app/services/           s3_service, extraction, classification, summarization, chunking,
                          embeddings, vector_store, rag_service, ingestion, bedrock, audit
  app/models/ schemas/ security/ config.py
  migrations/             Alembic
workers/
  ingest_lambda/          S3 upload event -> extraction -> AI pipeline (or start Textract)
  textract_callback/      Textract completion -> OCR text -> AI pipeline
infrastructure/terraform/ main, networking, ecs, rds, s3, iam, api_gateway, cognito, lambda,
                          monitoring, variables, outputs (+ bootstrap/ for state and CI role)
tests/                    test_documents, test_rag, test_security, test_ingestion
.github/workflows/        ci.yml, deploy.yml
```

## Run locally (no AWS account needed)

Requires Docker Desktop.

```bash
cp .env.example .env
docker compose up --build -d
```

Open http://localhost:5173 and sign in with the API key from `.env` (`local-demo-key-change-me`). That key has both the `hr-admin` and `employee` groups. If ports 5173/8000 are in use: `FRONTEND_PORT=15173 BACKEND_PORT=18000 docker compose up -d`.

Create the sample PDF and try the full flow:

```bash
docker compose run --rm --no-deps -v "$PWD/samples:/samples" backend python /samples/make_sample_pdf.py
```

1. **Document dashboard** → upload `samples/remote_work_expense_policy.pdf`. Its status moves to *Needs review*.
2. **Review** → check or edit the AI category and summary, choose who can see it → *Approve & publish*.
3. **Policy assistant** → ask *"Can I buy an ergonomic desk chair, and how much can I claim?"* Click the citation to open the PDF at the cited page.

> **Mock mode** (`AI_PROVIDER=mock`) is deterministic and offline: embeddings are token hashes and answers are the top retrieved excerpt. It shows the plumbing, not AI quality.

To use real Bedrock locally, set `AI_PROVIDER=bedrock` and `BEDROCK_CHAT_MODEL_ID` in `.env`, and make AWS credentials available to the backend container (for example a read-only mounted profile). Changing the embedding model requires reprocessing documents. `docker compose down -v` deletes all local data.

### Tests

```bash
docker compose --profile test run --rm tests        # pytest in the container against the compose Postgres
# or on the host (Python 3.12), from the repository root:
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://hrflow:hrflow_dev@localhost:5432/hrflow_test .venv/bin/python -m pytest -q
```

- `test_documents.py`: upload → processing → review edits → publish, validation, failures and reprocess, deletion, dashboard stats and audit trail.
- `test_rag.py`: only published evidence is used, citations (title, version, page, section, PDF link), follow-up questions, the model is never called without evidence, prompt construction, AI output parsing.
- `test_security.py`: API key and Cognito token checks (wrong client, ID token, expired, wrong issuer, forged signature), admin-only endpoints, group-based visibility in lists, downloads and retrieval, configuration guards.
- `test_ingestion.py`: chunking and headings, both Lambda handlers, and the async Textract flow (start, duplicate events, completion, failed job, transient error retried).

## Deploy to AWS

Everything is in `infrastructure/terraform`. **This creates billable resources** (roughly $80–120/month idle for the defaults: NAT gateway, RDS `db.t4g.micro`, internal ALB, 2 small Fargate tasks), plus Bedrock and Textract usage. Run `terraform destroy` when you are not demoing.

1. **Enable Bedrock model access** in your region for Titan Text Embeddings V2 and a Converse-compatible chat model. Note the model or inference-profile ID.
2. **Bootstrap once** (state bucket + GitHub OIDC deploy role), as an AWS administrator:
   ```bash
   cd infrastructure/terraform/bootstrap
   terraform init && terraform apply -var github_repository=YOUR_USER/hrflow-ai-knowledge-hub-aws
   ```
3. **In GitHub**, create an environment named `production` (add yourself as a required reviewer for a manual approval gate). Then add these repository variables: `AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET` (both are bootstrap outputs), `AWS_REGION` and `BEDROCK_CHAT_MODEL_ID`. `ENVIRONMENT` and `ALARM_EMAIL` are optional.
4. **Push to `main`.** After CI passes, *Deploy to AWS* builds and pushes the images, applies Terraform, waits for ECS, and smoke-tests `/health` and the 401 on `/api/documents`.
5. **Create users** with the `create_admin_user` command from `terraform output`, then open `terraform output app_url`.

Manual deploy from a laptop: `terraform init -backend-config=...` (same values as the workflow), push images tagged with a commit SHA to the three ECR repositories, then `terraform apply -var image_tag=<sha>` using `terraform.tfvars.example` as a template.

## Production readiness: what is and isn't done

Done in this repository: everything in the tables above, with tests.

Known limits and next steps:
- **Very large documents:** OCR runs asynchronously in Textract, but embedding happens in a single Lambda invocation (10-minute timeout, 100-page cap). For much larger documents, fan the embedding out across SQS messages, or use Step Functions or a Fargate worker.
- **API Gateway's 30-second integration timeout** limits chat. Long answers would need streaming (for example WebSockets or Lambda response streaming).
- **Retrieval quality:** add hybrid keyword + vector search, reranking, and an evaluation set of real policy questions with expected answers and pages before trusting answers about amounts or deadlines. The model is told to quote limits only from the evidence, and every answer shows its sources, but answers still need human-verifiable citations.
- **Security hardening:** scope the GitHub deploy role (currently AdministratorAccess, limited to the protected environment), add AWS WAF on API Gateway, use a KMS CMK for S3/RDS if required, and add malware scanning for uploads.
- **Operations:** NAT gateway per AZ, Multi-AZ RDS (`db_multi_az = true`), `deletion_protection = true`, a custom domain with ACM, and a retention policy for documents and audit events.
- Do not upload real employee data or PII until the above have been reviewed by your security team.

## API

| Method & path | Who | Purpose |
|---|---|---|
| `GET /health`, `/health/ready` | public | liveness / database readiness |
| `GET /api/config` | public | auth mode and Cognito settings for the SPA |
| `GET /api/me` | signed in | username, groups, admin flag |
| `GET /api/documents` | signed in | admins: all documents; others: published documents shared with their groups |
| `POST /api/documents` | hr-admin | create a record, returns a presigned S3 POST (or the local upload URL) |
| `POST /api/documents/{id}/file` | hr-admin | local storage only: upload the PDF |
| `GET /api/documents/{id}/source` | can see the document | short-lived link to the original PDF |
| `PATCH /api/documents/{id}/review` | hr-admin | approve (with edits) or reject |
| `POST /api/documents/{id}/reprocess` | hr-admin | re-run ingestion |
| `DELETE /api/documents/{id}` | hr-admin | delete the file, chunks and record |
| `POST /api/chat` | signed in | `{question, history}` → `{answer, sources[]}` |

Swagger UI is at http://localhost:8000/docs locally (it is disabled outside `ENVIRONMENT=local`).
