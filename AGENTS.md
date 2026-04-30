# OpenAgentd — Agent Instructions

On-machine AI assistant: FastAPI backend + React web UI.

## Tech stack

- **Backend:** Python 3.14, FastAPI, SQLModel, Pydantic v2, SQLite (WAL), SSE, loguru.
- **Frontend:** React 19, TypeScript 5, Vite, Bun, Tailwind v4, Zustand + Immer, TanStack Query.
- **Agent config:** `.md` files with YAML frontmatter in `.openagentd/agents/`.

## Layout

```
app/        FastAPI backend (agent/, api/, core/, models/, services/)
web/        React frontend
tests/      pytest suite
.openagentd/    Runtime data (agents/, skills/, chat/, team/)
documents/  All docs (see below)
```

## Commands (essentials)

```bash
# Backend
uv sync                           # install
make dev                          # run with reload on :8000
uv run ruff check app/ tests/     # lint
uv run ty check app/              # type check
uv run pytest --no-cov -q         # fast tests

# Frontend
cd web && bun dev                 # :5173, proxies /api → :8000
cd web && bun run lint && bun run typecheck && bun test src/__tests__
```

Full command reference: [`documents/docs/guidelines.md`](documents/docs/guidelines.md).

## Code style (summary)

- **Python 3.14+** — `|` unions, `from __future__ import annotations`, strict type hints, Pydantic v2, absolute imports from `app`, loguru `logger.info("event key={}", val)`.
- **TypeScript** — `strict: true`, functional components with explicit props, TanStack for server state, Zustand + Immer for client state, ESM only (Always mobile-first design)
- **General** — thin routes, logic in services/hooks, no unnecessary abstractions, always use the `guidelines` skill.

Full style guide: [`documents/docs/guidelines.md`](documents/docs/guidelines.md).

## Post-implementation checklist

```bash
uv run ruff check app/ tests/ && uv run ty check app/ && uv run pytest --no-cov -q
cd web && bun run lint && bun test src/__tests__     # if frontend changed
```

## Documentation map

Start at [`documents/docs/index.md`](documents/docs/index.md).

| Topic | Doc |
|-------|-----|
| Commands, code style, testing | [`docs/guidelines.md`](documents/docs/guidelines.md) |
| C4 diagrams, agent loop, SSE protocol | [`docs/architecture.md`](documents/docs/architecture.md) |
| Env vars, agent `.md` config, providers, sandbox | [`docs/configuration.md`](documents/docs/configuration.md) |
| Logging (app log, per-session, JSONL) | [`docs/logging.md`](documents/docs/logging.md) |
| Observability (OTel, DuckDB, `/telemetry`) | [`docs/observability.md`](documents/docs/observability.md) |
| Agent engine (loop, hooks, tools, teams, memory, plugins) | [`docs/agent/`](documents/docs/agent/) |
| HTTP routes, SSE events, file handling | [`docs/api/index.md`](documents/docs/api/index.md) |
| Tracked tech debt | [`techdebts/`](documents/techdebts/) |
