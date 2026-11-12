## What does this change?

<!-- A short summary of the change and why it is needed. -->

Closes #<!-- issue number, if any -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Infrastructure (Terraform / CI)

## How was it tested?

<!-- Commands you ran and what you checked by hand, e.g. upload → review → ask. -->

## Checklist

- [ ] `docker compose --profile test run --rm --build tests` passes
- [ ] `ruff check backend workers tests` passes
- [ ] `cd frontend && npm run build` passes (if the frontend changed)
- [ ] Tests added or updated for behaviour changes
- [ ] New database changes have a **new** migration with a `downgrade()`
- [ ] Retrieval and document access still filter by status and the caller's groups in SQL
- [ ] No secrets, `.env`, credentials or real employee data
- [ ] Docs updated (README / `docs/GETTING_STARTED.md`) if behaviour or setup changed
- [ ] `CHANGELOG.md` updated under `[Unreleased]` for user-visible changes

## AWS impact

- [ ] None
- [ ] Creates or resizes billable resources (describe below)
- [ ] Replaces or recreates existing resources (for example the database)

<!-- Screenshots for UI changes are very welcome. -->
