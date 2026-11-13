# Deploy to AWS from the command line

This guide deploys the whole stack from your terminal, **without GitHub Actions**: you build the container images yourself, push them to Amazon ECR, and run Terraform. Prefer automated deployments on every merge? Use [Part C of the getting started guide](GETTING_STARTED.md#part-c--deploy-to-aws) instead.

**Time:** about 45 minutes the first time (RDS creation takes 10–15 minutes of that).
**Cost:** roughly **$80–120 per month while idle** with the defaults (NAT gateway, RDS `db.t4g.micro`, internal load balancer, two small Fargate tasks), plus Bedrock and Textract usage. [Step 12](#step-12--tear-everything-down) removes it all.

What gets created: VPC, API Gateway, internal load balancer, ECS Fargate (`api` and `web` services), RDS PostgreSQL with pgvector, a private S3 bucket, SQS queues with dead-letter queues, SNS, two Lambda workers, Cognito, ECR repositories, and CloudWatch alarms and a dashboard.

---

## Step 1 — Install the tools

| Tool | Check | Install |
|---|---|---|
| Git | `git --version` | https://git-scm.com/downloads |
| Docker Desktop (with buildx) | `docker buildx version` | https://www.docker.com/products/docker-desktop |
| AWS CLI v2 | `aws --version` | `brew install awscli`, or https://aws.amazon.com/cli/ |
| Terraform ≥ 1.10 | `terraform -version` | https://developer.hashicorp.com/terraform/install |

**No Terraform?** Define this function in your shell and use `tf` wherever this guide says `terraform`. It runs Terraform in Docker with your AWS credentials and the current folder:

```bash
tf() { docker run --rm -it -v "$PWD":/w -w /w -v ~/.aws:/root/.aws \
  -e AWS_PROFILE -e AWS_REGION hashicorp/terraform:1.10 "$@"; }
```

## Step 2 — Get the code

```bash
git clone https://github.com/anisur-rahman/hrflow-ai-knowledge-hub-aws.git
cd hrflow-ai-knowledge-hub-aws
```

## Step 3 — Sign in to AWS

You need permissions to create IAM roles, VPCs and databases (administrator access is simplest).

```bash
aws configure sso          # IAM Identity Center (recommended), or:
aws configure              # access key of an IAM user

export AWS_PROFILE=default                # the profile name you just configured
export AWS_REGION=us-east-1               # region to deploy to
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Deploying to account $ACCOUNT_ID in $AWS_REGION"
```

Keep this terminal open: later steps use these variables.

## Step 4 — Choose, enable and test the Bedrock models

Follow **[Choosing the Amazon Bedrock models](BEDROCK_MODELS.md)**, steps 2–5: which chat model to pick (start with Claude Haiku 5.5), enabling model access, finding the exact ID for your region, and testing both models with the same settings the app uses. You finish with:

```bash
export MODEL_ID=<the inference profile ID or model ID that passed the test>
```

Optionally do its step 7 (lower effort for faster, cheaper answers) and add `bedrock_effort = "low"` to `terraform.tfvars` in Step 6.

## Step 5 — Create a bucket for the Terraform state

Terraform stores what it created in this bucket, so that you (or a teammate) can update or destroy the stack later.

```bash
export STATE_BUCKET=hrflow-tfstate-$ACCOUNT_ID

if [ "$AWS_REGION" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "$STATE_BUCKET"
else
  aws s3api create-bucket --bucket "$STATE_BUCKET" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION"
fi
aws s3api put-bucket-versioning --bucket "$STATE_BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket "$STATE_BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

> Already ran the GitHub Actions bootstrap (`infrastructure/terraform/bootstrap`)? It created this same bucket; skip this step.

## Step 6 — Configure the deployment

```bash
cd infrastructure/terraform

cat > terraform.tfvars <<EOF
environment           = "dev"
aws_region            = "$AWS_REGION"
bedrock_chat_model_id = "$MODEL_ID"
alarm_email           = ""        # optional: your email for CloudWatch alarms
EOF

terraform init \
  -backend-config="bucket=$STATE_BUCKET" \
  -backend-config="key=hrflow/dev.tfstate" \
  -backend-config="region=$AWS_REGION" \
  -backend-config="use_lockfile=true"
```

`terraform.tfvars` is git-ignored. Other settings (database size, Multi-AZ, deletion protection and more) are in `variables.tf`; add them to the file to change the defaults.

## Step 7 — Create the image repositories

The Lambda functions and ECS services need their images to exist before Terraform can create them, so create the three ECR repositories first:

```bash
export IMAGE_TAG=$(git rev-parse --short HEAD)
terraform apply -target=aws_ecr_repository.this -var image_tag=$IMAGE_TAG
```

Type `yes`. Terraform warns that `-target` is for exceptional use; that is expected here.

## Step 8 — Build and push the images

Run these from the **repository root**:

```bash
cd ../..
export REGISTRY=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"

# linux/amd64 matches the Fargate and Lambda architecture; --provenance=false keeps a
# single-platform manifest, which Lambda requires.
docker build --platform linux/amd64 --provenance=false -f backend/Dockerfile --target runtime \
  -t "$REGISTRY/hrflow-dev-api:$IMAGE_TAG" .
docker build --platform linux/amd64 --provenance=false -f workers/Dockerfile \
  -t "$REGISTRY/hrflow-dev-worker:$IMAGE_TAG" .
docker build --platform linux/amd64 --provenance=false \
  -t "$REGISTRY/hrflow-dev-web:$IMAGE_TAG" frontend

for image in api worker web; do docker push "$REGISTRY/hrflow-dev-$image:$IMAGE_TAG"; done
```

On Apple Silicon Macs the `linux/amd64` builds run under emulation and take a few extra minutes.

## Step 9 — Deploy everything

```bash
cd infrastructure/terraform
terraform plan -var image_tag=$IMAGE_TAG -out tfplan     # review what will be created
terraform apply tfplan                                   # about 15–20 minutes the first time
aws ecs wait services-stable --cluster hrflow-dev --services api web
```

The API applies the database migrations automatically when it starts.

**Smoke test:**

```bash
export APP_URL=$(terraform output -raw app_url)
curl -fsS "$APP_URL/health"; echo                                     # {"status":"ok"}
curl -fsS "$APP_URL/api/config" | head -c 120; echo                  # "auth_mode":"cognito",...
curl -s -o /dev/null -w '%{http_code}\n' "$APP_URL/api/documents"     # 401 (sign-in required)
echo "Open $APP_URL"
```

## Step 10 — Create users and sign in

```bash
export POOL_ID=$(terraform output -raw cognito_user_pool_id)

# An HR administrator (can upload, review and publish) who also has employee access
aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username jane.hr \
  --user-attributes Name=email,Value=jane@example.com Name=email_verified,Value=true
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL_ID" --username jane.hr --group-name hr-admin
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL_ID" --username jane.hr --group-name employee

# An employee (can only ask questions about published policies shared with "employee")
aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username sam.employee \
  --user-attributes Name=email,Value=sam@example.com Name=email_verified,Value=true
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL_ID" --username sam.employee --group-name employee
```

Use real email addresses: Cognito emails each user a temporary password. Then:

1. Open `$APP_URL` and click **Sign in with your company account**.
2. Enter the username and temporary password, then choose a new password (at least 12 characters, with upper and lower case letters, a number and a symbol).
3. As `jane.hr`: **Documents → Upload** a policy PDF (for example `samples/remote_work_expense_policy.pdf`, created with step A6 of the [getting started guide](GETTING_STARTED.md#a6-walk-through-the-whole-flow)), wait for *Needs review*, then **Review → Approve & publish**.
4. As `sam.employee`: ask a question in **Policy assistant** and click the citation.

## Step 11 — Operate and update

**Logs:**

```bash
aws logs tail /ecs/hrflow-dev/api --follow                   # API (JSON lines with request_id)
aws logs tail /aws/lambda/hrflow-dev-ingest --follow         # upload processing
aws logs tail /aws/lambda/hrflow-dev-textract-callback       # scanned PDFs (OCR)
```

**Dashboard and failed jobs:**

```bash
terraform output dashboard_url        # CloudWatch dashboard
terraform output dead_letter_queues   # messages that failed 3 times
```

**Deploy a new version** after changing code:

```bash
git commit -am "Describe the change"          # tags are immutable, so every deploy needs a new commit
export IMAGE_TAG=$(git rev-parse --short HEAD)
# repeat Step 8 (build and push), then:
cd infrastructure/terraform
terraform apply -var image_tag=$IMAGE_TAG
aws ecs wait services-stable --cluster hrflow-dev --services api web
```

ECS replaces the tasks one at a time and rolls back automatically if the new version fails its health checks.

## Step 12 — Tear everything down

```bash
cd infrastructure/terraform
terraform destroy -var image_tag=$IMAGE_TAG
```

Type `yes`. This deletes the database (no final snapshot while `deletion_protection = false`, the default), all uploaded documents, the images, the user pool and everything else in the stack.

Then delete the state bucket. Empty it first in the S3 console (select the bucket → **Empty**; it is versioned, so the console's Empty also removes old versions), then:

```bash
aws s3api delete-bucket --bucket "$STATE_BUCKET"
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ExpiredToken` or `The SSO session has expired` | `aws sso login`, then repeat the command |
| `docker push`: `no basic auth credentials` | The ECR login expires after 12 hours: rerun the `docker login` line from Step 8 |
| `tag invalid: The image tag ... already exists` | Tags are immutable. Commit your change and set a new `IMAGE_TAG` |
| Lambda: `image manifest ... not supported` | The image was built without `--platform linux/amd64 --provenance=false` |
| `terraform apply` fails creating the Lambda functions | The worker image is missing: run Step 8 for the same `IMAGE_TAG` |
| `Error acquiring the state lock` | Another apply is running, or one was interrupted. If you are sure nothing is running: `terraform force-unlock <LOCK_ID>` |
| ECS tasks keep restarting | `aws logs tail /ecs/hrflow-dev/api`: configuration errors are printed at startup |
| Sign-in shows `redirect_mismatch` | Open the app through `terraform output app_url` exactly (Cognito only allows that URL) |
| Chat says there is no relevant evidence | The document is not **published**, or not shared with the user's group |
| Bedrock `AccessDeniedException` or `ValidationException` in the logs | Model access, model ID or a setting the model rejects: rerun the tests in [Choosing the Amazon Bedrock models](BEDROCK_MODELS.md#5-test-the-models-the-way-the-application-calls-them) |
