---
name: fastapi-backend-project
description: "Repository-local workflow guidance for nontrivial FastAPI backend changes. Use when implementing or reviewing a feature that crosses router, service, repository, schema, async database, cache, exception, middleware, or public API boundaries in this template repository."
---

# FastAPI Backend Project

## Authority

- Follow the nearest [AGENTS.md](../../../AGENTS.md) as the policy and quality-gate authority.
- Treat implementation and tests as the final behavior source of truth.
- Treat the root and module README files as the current public contract.
- Use this skill for workflow and reference selection; do not use it as a second copy of repository rules or runtime defaults.

## Workflow

1. Inspect the affected call chain, nearby implementation, tests, configuration, and module documentation before designing the change.
2. Identify the public contract, business invariants, transaction boundary, failure modes, compatibility requirements, and documentation impact.
3. Reuse the repository's current abstractions after confirming their definitions; do not infer behavior from names or from this skill.
4. Keep the change scoped, update every affected layer, and preserve unrelated worktree changes.
5. Validate and report results according to `AGENTS.md`, including any unverified external-service or migration risk.

## Reference Routing

- Read [feature-workflow.md](references/feature-workflow.md) for a cross-layer feature, API change, cache integration, middleware change, or public contract review.
- Read [layered-feature-example.md](references/layered-feature-example.md) when a concrete router → service → repository implementation skeleton would help; adapt the placeholder domain instead of copying it as a runtime contract.
- Read [project-pattern-examples.md](references/project-pattern-examples.md) for project-specific pagination, unique-conflict conversion, cache consistency, or vertical-slice test examples.
- Read [async-data-access.md](references/async-data-access.md) for SQLAlchemy queries, transactions, models, relationships, repository changes, migrations, or concurrent database work.

Load current contracts directly when relevant:

- Project overview and runtime behavior: [README.md](../../../README.md)
- Responses and serialization: [app/schemas/README.md](../../../app/schemas/README.md)
- Exceptions and error responses: [app/exceptions/README.md](../../../app/exceptions/README.md)
- Cache behavior: [app/core/cache/README.md](../../../app/core/cache/README.md)
- Middleware behavior: [app/middlewares/README.md](../../../app/middlewares/README.md)
- Public enums: [app/enums/README.md](../../../app/enums/README.md)

## Project Adapters

- Confirm and prefer existing primitives such as `ResponseSchema`, `PageResponseSchema`, `PageDep`, project exceptions, `BaseRepository`, and the unified logging entry point.
- Treat reference code as an adaptation template, not proof that a module, route, field, default, or configuration is present in the current application.
- Discover current defaults, enabled components, routes, error codes, configuration requirements, and test layout from the repository instead of recording them in this skill.
- When code and documentation disagree, verify behavior from implementation and tests, then reconcile documentation within the requested scope.
- When the template evolves or is used to generate another project, follow that project's local instructions and current code rather than assuming this repository's present state.
