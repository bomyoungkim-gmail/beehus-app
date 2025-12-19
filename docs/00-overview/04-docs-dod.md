# Docs Definition of Done (DoD)
**Purpose:** Rules for when to update documentation to maintain consistency.
**Audience:** Devs reviewing PRs

## Update docs when:

- **Schema changes**: If you mock/change `mongo_models.py` -> update `/docs/04-data/00-schema.md`.
- **API changes**: If you add/change endpoints in `app/console` -> update `/docs/05-api/01-rest-contracts.md`.
- **Logic changes**: If you change how jobs are scheduled or retried -> update `/docs/02-business-rules/`.
- **Pipeline changes**: If you change `core/tasks.py` or Selenium logic -> update `/docs/07-jobs-and-ai/`.
- **UI changes**: If you change the console flows -> update `/docs/01-product/01-user-journeys.md`.
- **Architecture decisions**: If you make a significant tech choice -> create new ADR in `/docs/10-decisions/`.

## CI Checks
The `scripts/check_docs.py` script runs on CI to ensure:
1. `docs/` folder exists.
2. `00-overview/00-README.md` exists.
3. No broken relative links in markdown files.
