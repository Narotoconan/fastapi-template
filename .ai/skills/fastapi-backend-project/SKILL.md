---
name: fastapi-backend-project
description: "Project-level FastAPI backend guidance for projects generated from this template. Use when implementing, modifying, or reviewing this repository's routers, services, repositories, Pydantic schemas, async SQLAlchemy data access, unified responses, project exceptions, logging, Redis cache, rate limiting, middleware registration, tests, Ruff, or ty checks."
---

# FastAPI Backend Project

## Core Workflow

1. Read `AGENTS.md`, `README.md`, and the nearby files in the target module before editing.
2. Run `git status --short` and protect existing user changes.
3. Keep the request path as `router -> service -> repository`; do not place business rules or complex SQL in routers.
4. Keep all DB and I/O paths async: `async def`, `AsyncSession`, `await session.execute(...)`, and no blocking calls inside async functions.
5. Use project primitives: `ResponseSchema`, `PageResponseSchema`, `PageDep`, `BizException` subclasses, and `from app.core.log import log`.
6. Validate changed Python code with `uv run ruff format ...`, `uv run ruff check ...`, `uv run ty check`, and relevant `uv run pytest ...`.

## Reference Map

- Read `references/layered-feature-example.md` when adding or reshaping a feature across router, service, repository, schema, and route registration.
- Read `references/database-async-sqlalchemy.md` when writing async SQLAlchemy models, queries, transactions, eager loading, raw SQL, or repository methods.
- Read `references/error-handling.md` when choosing exception types, error codes, auth errors, validation errors, or middleware error responses.
- Read `references/cache-rate-limit.md` when using Redis cache, cache keys, cache decorators, or `@rate_limit(...)`.
- Read `references/testing-validation.md` before finishing code changes, adding tests, or deciding which checks to run.
- Read `references/anti-patterns.md` when reviewing code or correcting implementation that may violate project conventions.

## Layer Rules

### Router

- Define one `APIRouter` per feature file, usually `router_xxx = APIRouter(prefix="/xxx", tags=["..."])`.
- Keep handlers thin: accept path/query/body parameters, inject dependencies, call service, and wrap success responses.
- Use `PageDep` for pagination and `ResponseSchema.ok(...)` / `PageResponseSchema.ok(...)` for JSON APIs.
- Return `StreamingResponse` / `FileResponse` directly for file downloads; errors still go through project exceptions.
- If using `@rate_limit(...)`, place FastAPI route decorator above it and include a `request: Request` parameter.
- Export routers with `__all__`, then include them in `app/api/__init__.py`.

### Service

- Put business rules, permission decisions, orchestration, cache decisions, and transaction boundaries here.
- Do not use FastAPI `Depends` in service functions; pass explicit objects such as `AsyncSession`, current user id, and request DTOs.
- Raise project exceptions from `app.exceptions`; avoid `HTTPException` in service code.
- For write flows, start `async with session.begin():` before the first DB operation that belongs to the write transaction; repositories should not commit or rollback.
- Return response schemas or domain-shaped data that routers can directly wrap.

### Repository

- Put SQLAlchemy statements and persistence details here.
- Follow the current `BaseRepository` singleton style and pass `AsyncSession` into repository methods.
- Use SQLAlchemy 2.0 statements such as `select(...)`, `update(...)`, `delete(...)`; do not use sync `Session` or `session.query(...)`.
- Repository methods should be async when they touch DB, should not know HTTP concepts, and should normally return ORM objects, primitives, `None`, or tuples for the service to interpret.
- Avoid N+1 queries; use joins, `selectinload`, or explicit batch queries when relationships are needed.

## Error And Logging Rules

- Use `NotFoundException` for missing resources, `ParamsException` for semantic parameter errors, `AuthException` / `ForbiddenException` for authz, and `BizException(ErrorCode.ALREADY_EXISTS, ...)` or other `ErrorCode` values for business failures.
- Let global handlers in `app.exceptions.handlers` build error responses; do not manually return failed `ResponseSchema` from business code.
- Log through `from app.core.log import log` only; allowed methods are `log.info`, `log.warning`, `log.error`, and `log.debug`.
- Never log passwords, tokens, secrets, ID numbers, phone numbers, or raw credential-bearing headers.

## Schema Rules

- Request/response models live in `app/schemas/` and inherit `BaseSchema`.
- Use Pydantic `Field(...)` for validation, descriptions, and OpenAPI clarity.
- Put shared enum values in `app/enums/`; do not duplicate enum definitions in schemas or services.
- For ORM-to-response conversion with `model_validate(orm_obj)`, add `model_config = ConfigDict(from_attributes=True)` to the response schema.
- Prefer meaningful model names such as `OrderCreate`, `OrderSearch`, `OrderResponse`; avoid generic names like `Data` or `Result`.

## Project Conventions

- Use Python 3.12 typing: `list[str]`, `dict[str, Any]`, `X | None`, and `collections.abc.Callable`.
- Sort imports as standard library, third-party, then `app` / `config`.
- Add Chinese docstrings to new or meaningfully changed functions containing business logic.
- Keep configuration in `config/`; do not modify `.env`, `.env.*`, real secrets, or production credentials.
- Preserve `main.py` initialization order: settings, logging, FastAPI app, exception handlers, rate limiter, middleware, routers.

## Best Practice Anchors

- Use FastAPI `APIRouter` to structure larger applications into multiple files.
- Use FastAPI dependencies for request-bound resources such as DB sessions and pagination, then pass resolved objects to services explicitly.
- Centralize exception handlers so route/service code raises domain errors instead of hand-building failed JSON.
- Treat each `AsyncSession` as request/task-scoped and do not share it concurrently across asyncio tasks.
