# Getting started: step by step

This guide takes you from an empty machine to:

1. **[Part A](#part-a--run-it-locally-15-minutes-no-aws-account)**: the app running on your laptop (no AWS account, no cost).
2. **[Part B](#part-b--develop-and-contribute)**: changing code, running tests and opening a pull request.
3. **[Part C](#part-c--deploy-to-aws)**: a full deployment to your own AWS account through GitHub Actions. Or deploy [from the command line](DEPLOY_AWS_CLI.md) without GitHub Actions.
4. **[Part D](#part-d--tear-down-aws)**: removing everything from AWS again.

Commands are for macOS or Linux (on Windows, use WSL 2). Lines starting with `#` are comments.

---

## Part A — Run it locally (15 minutes, no AWS account)

### A1. Install the prerequisites

| Tool | Version | Check | Install |
|---|---|---|---|
| Git | any recent | `git --version` | https://git-scm.com/downloads |
| Docker Desktop | 4.x (Compose v2) | `docker compose version` | https://www.docker.com/products/docker-desktop |

Start Docker Desktop and wait until it reports that it is running.

### A2. Get the code

```bash
git clone https://github.com/anisur-rahman/hrflow-ai-knowledge-hub-aws.git
cd hrflow-ai-knowledge-hub-aws
```

> Planning to deploy or contribute? **Fork** the repository on GitHub first (top-right **Fork** button) and clone your fork instead.

### A3. Create your local settings

```bash
cp .env.example .env
```

The defaults run entirely offline:

| Setting | Default | Meaning |
|---|---|---|
| `AI_PROVIDER` | `mock` | No Bedrock calls; deterministic stand-in embeddings and answers |
| `STORAGE_PROVIDER` | `local` | PDFs stored in a Docker volume instead of S3 |
| `AUTH_MODE` | `apikey` | One local API key instead of Cognito |
| `API_KEY` | `local-demo-key-change-me` | That key; it has the `hr-admin` and `employee` groups |

`.env` is git-ignored; never commit it.

### A4. Start the stack

```bash
docker compose up --build -d
docker compose ps          # postgres, backend and frontend should be "Up"/"healthy"
curl http://localhost:8000/health/ready     # {"status":"ready"}
```

The first build takes a few minutes. The backend runs the database migrations automatically on start.

**Don't want to build?** Use the images published for each release on GitHub Container Registry. They are multi-architecture, so they run natively on Apple Silicon too:

```bash
docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d
HRFLOW_VERSION=1.0.0 docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d   # a specific release
```

**Port already in use?** Another project may be using 5173 or 8000. Choose different ports:

```bash
FRONTEND_PORT=15173 BACKEND_PORT=18000 docker compose up --build -d
# then use http://localhost:15173 and http://localhost:18000 below
```

### A5. Sign in

Open **http://localhost:5173** and click **Use demo key**.

![Sign-in page](screenshots/02-sign-in-demo-key.png)

### A6. Walk through the whole flow

1. **Create the sample policy PDF:**
   ```bash
   docker compose run --rm --no-deps -v "$PWD/samples:/samples" backend python /samples/make_sample_pdf.py
   ```
   This writes `samples/remote_work_expense_policy.pdf`.
2. **Upload it:** go to **Documents**, choose the PDF, keep *Visible to: employee*, and click **Upload & process**. Within a few seconds the status changes from *Extracting* to *Needs review*.
3. **Review and publish it:** click **Review**, check (or edit) the AI category and summary, and click **Approve & publish**. Employees can only get answers from published documents.
4. **Ask a question:** open **Policy assistant** and ask *"Can I buy an ergonomic desk chair, and how much can I claim?"* The answer cites the policy, its version, the page and the section. Click the citation to open the PDF at that page.
5. **See the HR view:** **Dashboard** shows the review queue, failures, question counts and the audit trail.

![HR dashboard](screenshots/03-hr-dashboard.png)

> In mock mode an answer is the best matching excerpt, not generated text. Part C (or step B5) switches to real Bedrock AI.

### A7. Stop or reset

```bash
docker compose down        # stop (keeps your data)
docker compose down -v     # stop AND delete the database and uploaded files
```

---

## Part B — Develop and contribute

### B1. Run the tests

The easiest way is in Docker, against a real PostgreSQL + pgvector:

```bash
docker compose --profile test run --rm --build tests
```

Or on your machine (needs Python 3.12 and a reachable PostgreSQL with pgvector):

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://hrflow:hrflow_dev@localhost:5432/hrflow_test .venv/bin/python -m pytest -q
.venv/bin/ruff check backend workers tests
```

Frontend type checks and the production build (needs Node.js 22):

```bash
cd frontend && npm ci && npm run build
```

### B2. Frontend with hot reload

Keep the Docker stack running (the backend must be on port 8000), then:

```bash
cd frontend
npm ci
npm run dev                # http://localhost:5173, proxies /api to localhost:8000
```

If 5173 is taken by the Docker frontend, either stop that container (`docker compose stop frontend`) or let Vite choose the next free port.

### B3. Backend changes

The backend runs in Docker. Rebuild it after editing Python code:

```bash
docker compose up --build -d backend
docker compose logs -f backend      # JSON logs with a request_id on every line
```

API docs (Swagger) are at http://localhost:8000/docs.

### B4. Database changes

1. Change the SQLAlchemy model in `backend/app/models/`.
2. Add a migration in `backend/migrations/versions/`, numbered after the last one (see `0002_textract_callback.py` for the pattern: `revision`, `down_revision`, `upgrade()`, `downgrade()`).
3. `docker compose up --build -d backend` applies it; the tests apply it to the test database.

### B5. (Optional) Use real Bedrock AI locally

Complete steps C1–C2 first (AWS CLI signed in, model access enabled). Then:

```bash
# .env
AI_PROVIDER=bedrock
BEDROCK_CHAT_MODEL_ID=<model or inference profile ID from step C2>
BEDROCK_EFFORT=                 # optional, see docs/BEDROCK_MODELS.md step 7
```

Make your AWS credentials available to the backend container by creating `docker-compose.override.yml` (Compose loads it automatically; it is yours, so don't commit it):

```yaml
services:
  backend:
    volumes:
      - ~/.aws:/aws
    environment:
      AWS_CONFIG_FILE: /aws/config
      AWS_SHARED_CREDENTIALS_FILE: /aws/credentials
      AWS_PROFILE: default        # or your SSO profile name
```

```bash
docker compose up -d backend
```

Existing documents were embedded with the mock model, so **Reprocess** them (or `docker compose down -v` and upload again).

### B6. Contribution workflow

```bash
git checkout -b feature/short-description
# ...make changes, run B1...
git commit -m "Describe the change"
git push -u origin feature/short-description
```

Open a pull request on GitHub (see [CONTRIBUTING.md](../CONTRIBUTING.md) for the standards). **CI** runs automatically: ruff, pytest against pgvector, the frontend type check and build, `npm audit`, `terraform validate`, and Docker image builds. All checks must pass before you merge.

---

## Part C — Deploy to AWS

> **Prefer to deploy from your terminal without GitHub Actions?** Follow [Deploy to AWS from the command line](DEPLOY_AWS_CLI.md) instead.

What gets created: VPC, API Gateway, internal load balancer, ECS Fargate (`api`, `web`), RDS PostgreSQL, S3, SQS + DLQs, SNS, two Lambda workers, Cognito, ECR and CloudWatch alarms and dashboard. See the [architecture](../README.md#architecture).

> **Cost:** roughly **$80–120 per month while idle** with the defaults (NAT gateway, RDS `db.t4g.micro`, load balancer, two small Fargate tasks), plus Bedrock and Textract usage. Run [Part D](#part-d--tear-down-aws) when you are done.

### C1. Prepare your tools and sign in to AWS

You need an AWS account where you can create IAM roles (administrator access), and:

| Tool | Check | Install |
|---|---|---|
| AWS CLI v2 | `aws --version` | `brew install awscli`, or https://aws.amazon.com/cli/ |
| Terraform ≥ 1.10 | `terraform -version` | https://developer.hashicorp.com/terraform/install (or use Docker, below) |
| GitHub CLI (optional) | `gh --version` | `brew install gh`, then `gh auth login` |

Sign the CLI in to your account:

```bash
aws configure sso          # if your organization uses IAM Identity Center (recommended)
# or
aws configure              # access key of an IAM user with admin rights

aws sts get-caller-identity   # must show your account ID
```

**No Terraform installed?** Use this function in every step below instead. It runs Terraform in Docker with your AWS credentials:

```bash
tf() { docker run --rm -it -v "$PWD":/w -w /w -v ~/.aws:/root/.aws \
  -e AWS_PROFILE -e AWS_REGION hashicorp/terraform:1.10 "$@"; }
# then write `tf init` instead of `terraform init`, and so on
```

### C2. Choose, enable and test the Bedrock models

Follow **[Choosing the Amazon Bedrock models](BEDROCK_MODELS.md)**, steps 2–5: pick the chat model (start with Claude Haiku 5.5), enable model access, find the exact ID for your region, and test both models the way the app calls them. Keep the ID that passed the test for step C4.

### C3. Bootstrap once: Terraform state and the GitHub deploy role

This creates an S3 bucket for Terraform state, and an IAM role that **only** GitHub Actions jobs in your repository's `production` environment can assume. GitHub never stores AWS keys.

```bash
cd infrastructure/terraform/bootstrap
terraform init
terraform apply \
  -var github_repository=YOUR_GITHUB_USER/hrflow-ai-knowledge-hub-aws \
  -var aws_region=us-east-1
```

Type `yes` to confirm, then copy the two outputs: `state_bucket` and `deploy_role_arn`.

> **"EntityAlreadyExists: Provider with url https://token.actions.githubusercontent.com"?** Your account already has the GitHub OIDC provider. Import it, then run the apply again:
> `terraform import aws_iam_openid_connect_provider.github arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com`

Keep the local `terraform.tfstate` from this folder somewhere safe (it is git-ignored). You need it to change or destroy the bootstrap resources later.

### C4. Configure GitHub

**a) Create the `production` environment.** In your repository, go to **Settings → Environments → New environment**, name it `production`, and under **Required reviewers** add yourself. Every deployment will then wait for your approval.

**b) Add the repository variables.** Go to **Settings → Secrets and variables → Actions → Variables**, or use the GitHub CLI:

```bash
gh variable set AWS_DEPLOY_ROLE_ARN   --body "<deploy_role_arn from C3>"
gh variable set TF_STATE_BUCKET       --body "<state_bucket from C3>"
gh variable set AWS_REGION            --body "us-east-1"
gh variable set BEDROCK_CHAT_MODEL_ID --body "<chat model or inference profile ID from C2>"
gh variable set ENVIRONMENT           --body "dev"               # optional; names resources hrflow-dev-*
gh variable set ALARM_EMAIL           --body "you@example.com"   # optional; alarm notifications
gh variable set BEDROCK_EFFORT        --body "low"               # optional; only after the check in BEDROCK_MODELS.md step 7
```

These are not secrets. The workflow has no AWS keys at all; it signs in with GitHub OIDC.

### C5. Deploy

Deployments run automatically after CI passes on `main`. To start the first one now:

```bash
gh workflow run deploy.yml       # or GitHub → Actions → "Deploy to AWS" → Run workflow
```

Then go to **Actions → Deploy to AWS**, open the run and click **Review deployments → Approve**. The workflow:

1. creates the ECR repositories (first run only);
2. builds and pushes the `api`, `worker` and `web` images, tagged with the commit SHA;
3. runs `terraform plan` and `terraform apply` (about 15–20 minutes the first time, mostly RDS);
4. waits for the ECS services to become stable;
5. smoke-tests `/health`, `/api/config`, and checks that `/api/documents` returns 401 without a token.

The end of the log shows `Deployed <sha> to https://xxxx.execute-api.<region>.amazonaws.com`.

### C6. Create users

Read the outputs from your machine (same backend settings as the workflow):

```bash
cd infrastructure/terraform
terraform init \
  -backend-config="bucket=<state_bucket>" \
  -backend-config="key=hrflow/dev.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="use_lockfile=true"
terraform output app_url
terraform output -raw create_admin_user
```

Run the printed commands, replacing `jane.hr` and the email with real values. Cognito emails a temporary password. To add an employee-only user, repeat with `--group-name employee` only.

### C7. Use and verify the deployment

1. Open `app_url`, click **Sign in with your company account**, enter the username and temporary password, and set a new password.
2. Upload the sample PDF from step A6. In AWS the browser sends it **directly to S3**, then S3 → SQS → the `ingest` Lambda processes it. Scanned PDFs go through Textract → SNS → the `textract-callback` Lambda.
3. Review and publish it, then ask a question as in A6. The answer is now generated by Bedrock from the cited pages.
4. Monitoring: `terraform output dashboard_url` opens the CloudWatch dashboard. If you set `ALARM_EMAIL`, confirm the SNS subscription email so alarms reach you.

### C8. Ship changes

Merge to `main` → CI → **Deploy to AWS** (after your approval) → new images and a rolling ECS update. Database migrations run automatically when the API starts, protected by a Postgres advisory lock.

---

## Part D — Tear down AWS

```bash
cd infrastructure/terraform          # after the `terraform init` from C6
terraform destroy \
  -var image_tag=$(git rev-parse HEAD) \
  -var bedrock_chat_model_id=<same ID as BEDROCK_CHAT_MODEL_ID> \
  -var aws_region=us-east-1
```

This deletes the database (without a final snapshot while `deletion_protection = false`, the default), the documents bucket, the ECR images and everything else in the main stack. Set `deletion_protection = true` before you store real data.

Optionally remove the bootstrap resources too. Empty the versioned state bucket first (S3 console → bucket → **Empty**), then:

```bash
cd bootstrap && terraform destroy -var github_repository=YOUR_GITHUB_USER/hrflow-ai-knowledge-hub-aws
```

Finally, delete the GitHub variables so the deploy workflow goes back to being skipped.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` | Use other ports: `FRONTEND_PORT=15173 BACKEND_PORT=18000 docker compose up -d` |
| Backend restarts with a migration error after pulling changes | Your local database predates a migration: `docker compose down -v` (deletes local data), then `up` again |
| Sign-in page has no **Use demo key** button | You changed `API_KEY` in `.env`; type your key instead |
| Upload ends as *Failed: No selectable text found* | It is a scanned PDF; locally there is no OCR. In AWS, Textract handles it |
| Chat answers "I could not find relevant policy evidence…" | The document is not **published**, or it is not visible to your groups |
| *Deploy to AWS* shows **skipped** | `AWS_DEPLOY_ROLE_ARN` is not set (C4), or CI failed |
| Deploy fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity` | `github_repository` in C3 must exactly match `owner/repo`, and the job must use the `production` environment |
| Bedrock `AccessDeniedException` or `ValidationException` in the logs | Model access, model ID or a setting the model rejects: rerun the tests in [Choosing the Amazon Bedrock models](BEDROCK_MODELS.md#5-test-the-models-the-way-the-application-calls-them) |
| ECS tasks keep restarting | CloudWatch Logs → `/ecs/hrflow-dev/api`; usually a configuration error, which is printed on startup |
| Documents stuck in *Extracting* / *OCR running* | Check the `ingest` / `textract-callback` Lambda logs and the DLQs (`terraform output dead_letter_queues`); use **Reprocess** after one hour |
