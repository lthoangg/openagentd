# Contributing to openagentd

Thanks for your interest in contributing. This guide covers everything you need to get started.

**License note:** openagentd is licensed under [Apache License 2.0](LICENSE). By contributing you agree your work is released under the same license.

---

## What gets merged

- Bug fixes
- New LLM providers
- Documentation improvements
- Test coverage improvements
- Developer experience improvements

UI changes and new core features require discussion first — open an issue before writing code.

---

## Table of contents

- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Development workflow](#development-workflow)
- [Code style](#code-style)
- [Testing](#testing)
- [Submitting changes](#submitting-changes)
- [Issue labels](#issue-labels)

---

## Quick start

```bash
# 1. Fork + clone
git clone https://github.com/<your-fork>/openagentd.git
cd openagentd

# 2. Install deps
uv sync
bun install --cwd web

# 3. First-time setup (provider, API key, config files)
openagentd init --dev

# 4. Start the backend
make run

# 5. (Optional) Start the web UI in a separate terminal
cd web && bun dev
```

See [Configuration](documents/docs/configuration.md) for the full env var reference.

---

## Project layout

```
openagentd/
├── app/                    # FastAPI backend
│   ├── agent/              # Agent loop, hooks, providers, tools, teams
│   ├── api/                # Routes (thin — logic lives in services/)
│   ├── core/               # Config, DB, middleware, logging
│   ├── models/             # SQLModel DB schemas
│   └── services/           # Business logic, stream_store
├── web/                    # React 19 frontend (Vite + Bun)
├── tests/                  # pytest test suite
├── seed/                   # Default config copied on first init
│   ├── agents/             # Seed agent .md files (lead + members)
│   └── skills/             # Seed skill SKILL.md files
    └── documents/              # All documentation
        ├── docs/               # Architecture, configuration, guidelines
        └── styling-specs/      # Design tokens and visual specifications
```

Skills and agents at runtime live in `{OPENAGENTD_CONFIG_DIR}/agents/` and `{OPENAGENTD_CONFIG_DIR}/skills/` (populated from `seed/` on first `openagentd init`).

Key design rules:

- **Route handlers are thin** — business logic belongs in `services/`.
- **All agent code lives under `app/agent/`** — never scatter into top-level packages.
- **`stream_store.init_turn()` is called synchronously** before the background task starts — no producer/consumer race.

---

## Development workflow

### Backend

```bash
uv sync                                  # install / sync Python deps
make run                                 # start server on :8000
make dev                                 # with auto-reload

uv run ruff check app/ tests/            # lint
uv run ruff check app/ tests/ --fix      # auto-fix
uv run ruff format app/ tests/           # format
uv run ty check app/                     # type check

uv run pytest --no-cov -q               # fast tests
uv run pytest                            # full run with coverage (htmlcov/)
```

### Frontend (web)

```bash
cd web
bun dev                                  # dev server on :5173 (proxies /api → :8000)
bun run lint                             # eslint
bun run typecheck                        # tsc --noEmit
bun test src/__tests__                   # unit tests
bun run build                            # production build
```

### Database migrations

Migrations run automatically when the server starts — no manual step needed. For development, you can still run them directly:

```bash
uv run alembic -c app/alembic.ini upgrade head
```

---

## Code style

### Python

- **Python 3.14+** — use `|` for unions, `from __future__ import annotations` in every file.
- Strict type hints on all function signatures.
- Pydantic v2 for all data models (`ConfigDict(extra="ignore")` for external responses).
- `snake_case` for modules/functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Logging with **loguru**: `logger.info("event_name key={} key2={}", val, val2)`.
- Absolute imports from `app` (e.g. `from app.agent.schemas.chat import ChatMessage`).

### TypeScript

- Strict TypeScript (`strict: true`).
- Functional React components with explicit prop types.
- TanStack Query for server state, Zustand + Immer for client state.

### General

- **No unnecessary abstractions.** Thin routes, logic in services/hooks.
- Pre-commit hooks enforce formatting automatically — install them once:

  ```bash
  uv run pre-commit install
  ```

---

## Testing

### Backend

Tests mirror the `app/` structure under `tests/`. Key patterns:

- `conftest.py` redirects to in-memory SQLite — no external DB needed.
- In-memory SQLite and `AsyncMock` for all external dependencies — no external services needed in unit tests.
- `app.dependency_overrides` for FastAPI dependency injection.

Coverage target: **≥ 80%** for `app/agent/` and `app/api/`.

```bash
uv run pytest --no-cov -q               # quick pass/fail
uv run pytest                            # full with HTML coverage report
open htmlcov/index.html
```

### Frontend

```bash
cd web && bun test src/__tests__         # ~130 ms, no browser needed
```

Tests use Bun test + Happy DOM. Test store logic and pure utils directly; avoid rendering components in unit tests.

---

## Submitting changes

1. **Open an issue first** for anything non-trivial — discuss the approach before writing code.
2. **Branch naming:** `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `refactor/<topic>`.
3. **Before opening a PR:**
   - `uv run ruff check app/ tests/` passes
   - `uv run ty check app/` passes
   - `uv run pytest --no-cov -q` passes
   - `cd web && bun run lint && bun test src/__tests__` passes
4. **Commit style:** [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
5. **PR description:**

   ```
   ## Changes
   ## Why
   ## Testing
   Fixes #<issue>
   ```

6. Keep PRs focused — one logical change per PR.

---

## Issue labels

| Label | Meaning |
|-------|---------|
| `bug` | Something is broken |
| `feature` | New capability |
| `docs` | Documentation update |
| `devex` | Developer experience improvement |
| `question` | Usage question (closed after answering) |

---

## Documentation

All docs live in `documents/`. Start at [`documents/docs/index.md`](documents/docs/index.md).
