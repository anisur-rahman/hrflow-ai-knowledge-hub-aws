# Contributing to HRFlow AI Knowledge Hub

Thanks for your interest in improving this project! This page explains how to propose changes and what a pull request needs before it can be merged.

## Ways to contribute

- **Report a bug:** open an [issue](https://github.com/anisur-rahman/hrflow-ai-knowledge-hub-aws/issues) with the steps to reproduce, what you expected, what happened, and the relevant log lines (`docker compose logs backend`; every line has a `request_id`).
- **Suggest a feature:** open an issue describing the problem you want solved before writing a large change, so the approach can be agreed first.
- **Improve the docs:** fixes to the README or the [step-by-step guide](docs/GETTING_STARTED.md) are always welcome.
- **Send code:** follow the workflow below.

**Security problems:** please do **not** open a public issue. Contact the maintainer privately through their [GitHub profile](https://github.com/anisur-rahman) and allow time for a fix before anything is disclosed.

## Development setup

Follow [Part A](docs/GETTING_STARTED.md#part-a--run-it-locally-15-minutes-no-aws-account) of the guide to run the app locally (Docker only, no AWS account needed), and [Part B](docs/GETTING_STARTED.md#part-b--develop-and-contribute) for tests, hot reload and migrations.

## Workflow

1. **Fork** the repository and clone your fork.
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/short-description      # or fix/..., docs/...
   ```
3. **Make your change**, with tests (see [Standards](#standards)).
4. **Run the checks locally** (the same ones CI runs):
   ```bash
   docker compose --profile test run --rm --build tests     # backend + worker tests on PostgreSQL + pgvector
   ruff check backend workers tests                         # Python lint (needs requirements-dev)
   (cd frontend && npm ci && npm run build)                 # type check + production build
   terraform -chdir=infrastructure/terraform fmt -check -recursive   # if you touched Terraform
   ```
5. **Commit** with a clear message: a short summary line in the imperative mood ("Add …", "Fix …"), and a body explaining *why* if the change is not obvious.
6. **Push and open a pull request** against `main`. Describe what changed and how you tested it, and link the issue it addresses.

CI must pass (lint, tests, frontend build, `npm audit`, `terraform validate`, image builds) before a pull request can be merged. Keep pull requests focused: one change per pull request is much easier to review.

## Standards

### Python (backend and workers)
- Python 3.12, formatted for [Ruff](https://docs.astral.sh/ruff/) with the settings in `pyproject.toml` (line length 125).
- Put business logic in `backend/app/services/`. Keep `api/` routers thin, and keep the Lambda handlers in `workers/` as thin adapters over the same services.
- Use type hints on public functions. Request and response shapes belong in `backend/app/schemas/`.
- Log with `log_event('area.event', key=value)` rather than `print`; CloudWatch metrics are built from these events.

### Frontend
- Vue 3 `<script setup lang="ts">` with PrimeVue components. `npm run build` must pass `vue-tsc` with no errors.
- Keep API calls in `src/services/api.ts`; views compose components and services.

### Tests
- Every behaviour change needs a test in `tests/`: `test_documents.py`, `test_rag.py`, `test_security.py` or `test_ingestion.py`, whichever fits.
- The tests use the real database, so prefer an API-level test over mocking SQL. Mock only external services (Bedrock, Textract, S3), as the existing tests do.

### Database
- Never edit an existing migration. Add a new file in `backend/migrations/versions/` that follows the numbering, and include a `downgrade()`.

### Security rules (non-negotiable)
- **Authorization before the LLM:** any new retrieval path must filter by document status and the caller's groups in SQL (see `backend/app/security/access.py`).
- Never commit secrets, `.env`, credentials, Terraform state or real employee data. Test documents must be fictitious.
- IAM changes in Terraform should grant the narrowest actions and resources that work.

## Infrastructure changes

Run `terraform fmt` and `terraform validate` (see the guide if Terraform is not installed). Say in the pull request if the change creates new billable resources or replaces existing ones (for example, anything that would recreate the database).

## License

By contributing, you agree that your contributions are licensed under the project's [MIT License](LICENSE).
