# Security policy

## Supported versions

Security fixes are made on the `main` branch only. If you deployed an older commit, update to the latest `main` (see the [command-line](docs/DEPLOY_AWS_CLI.md#step-11--operate-and-update) or [GitHub Actions](docs/GETTING_STARTED.md#c8-ship-changes) deployment guide).

## Reporting a vulnerability

**Please do not report security problems in public issues, pull requests or discussions.**

Email **[anisur_rahman@outlook.com](mailto:anisur_rahman@outlook.com)** with the subject `SECURITY: <short summary>` and include:

- what the problem is and its impact (for example, "an employee can read an unpublished document");
- the steps or a minimal proof of concept to reproduce it;
- the affected commit (`git rev-parse --short HEAD`) and where you saw it: local Docker Compose or an AWS deployment;
- any logs, with secrets and personal data removed.

What to expect:

- an acknowledgement within **5 business days**;
- an assessment, and a plan or a request for more details, after that;
- coordinated disclosure: please allow time for a fix before sharing details publicly. You will be credited in the fix unless you prefer not to be.

This is a personal open-source project maintained on a best-effort basis; there is no bug bounty.

## Scope

**In scope:** the code in this repository: the FastAPI backend, the Lambda workers, the Vue frontend, the Terraform configuration and the GitHub Actions workflows.

Examples of what to report:

- bypassing authentication, or using another user's identity;
- reading, retrieving or being answered from documents that are unpublished or not shared with your groups;
- prompt injection that makes the assistant reveal unauthorized content or act outside its instructions;
- injection, path traversal, or server-side request forgery;
- overly broad IAM permissions or public exposure in the Terraform configuration.

**Out of scope:**

- the local demo mode's single, well-known API key (`AUTH_MODE=apikey`, refused when `ENVIRONMENT` is not `local`);
- vulnerabilities in AWS services or in third-party dependencies themselves (report those upstream, but do tell us if this project uses them insecurely);
- denial-of-service or load testing against someone else's deployment;
- findings that need physical access or an already compromised AWS account.

Only test against **your own** deployment, never one you do not own.

## How the application is secured

| Area | Control |
|---|---|
| Sign-in | Amazon Cognito (authorization code + PKCE, no client secret in the browser), optional MFA, admin-created accounts only |
| API authentication | API Gateway's JWT authorizer, and the API verifies the Cognito access token again (signature, issuer, expiry, client ID, token type) |
| Authorization | HR-only endpoints require the `hr-admin` group. Document access is filtered in SQL by publication status and the caller's groups **before** any text reaches the LLM |
| AI safety | Only published, authorized evidence is sent to Bedrock. Prompts treat documents as untrusted data, and the model is never called without evidence. Answers show their sources |
| Uploads | Size and type limits enforced by presigned S3 POST conditions and checked again by the worker; PDF signature check; page limit |
| Data | Private S3 bucket (TLS-only policy, encryption, versioning, public access blocked), encrypted RDS in private subnets, SQS encryption |
| Secrets | The database password is managed by Secrets Manager. GitHub deploys through OIDC, so no long-lived AWS keys are stored anywhere |
| Infrastructure | Least-privilege IAM roles per service; the load balancer is internal and reachable only through API Gateway |
| Web | Content Security Policy, `X-Frame-Options: DENY`, `nosniff` and a strict referrer policy |
| Supply chain | CI runs `npm audit`; ECR scans images on push |
| Audit | Uploads, reviews, deletions, opened sources and questions are recorded in an audit table |

## Known limitations

Before using this with real employee data, review the [production readiness notes](README.md#production-readiness-what-is-and-isnt-done). In particular:

- the GitHub deploy role has `AdministratorAccess` (it can only be assumed by the protected `production` environment); scope it down;
- there is no AWS WAF on API Gateway, and no malware scanning of uploaded files;
- S3 and RDS use AWS-managed encryption keys rather than a customer-managed KMS key;
- API rate limiting is the API Gateway stage throttle only.
