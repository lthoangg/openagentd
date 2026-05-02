# Install

openagentd ships as a single Python package that includes the pre-built web UI. No Node, no Bun, no separate frontend process — one process, one port.

## uv (recommended)

```bash
uv tool install openagentd
```

Installs `openagentd` into an isolated tool venv managed by [uv](https://docs.astral.sh/uv/), and puts the binary on your `PATH`. This is the recommended path on every OS.

## pipx

```bash
pipx install openagentd
```

Same isolation model as `uv tool`, slower install. Use this if you already have pipx and don't want another tool.

## pip

```bash
pip install --user openagentd
```

Works on Linux distros and Python builds without [PEP 668](https://peps.python.org/pep-0668/) protection. On **macOS Homebrew Python**, **Debian/Ubuntu system Python**, and most modern distros, `pip install` will refuse with an `externally-managed-environment` error — use `uv tool install` or `pipx install` above instead, or create a venv first.

## Homebrew (macOS / Linux)

```bash
brew tap lthoangg/tap
brew install openagentd
```

To upgrade:

```bash
openagentd upgrade      # via the built-in upgrade command
# or directly:
brew upgrade openagentd
```

> **Note:** On first install or after a `brew reinstall`, you may see a warning about
> `Failed changing dylib ID` for the `cryptography` package. This is a cosmetic Homebrew
> relinking warning — openagentd still works correctly. Run `brew update` before
> reinstalling to ensure the latest formula is used.

## Docker

```bash
# Clone the repo (for docker-compose.yaml and .env.example)
git clone https://github.com/lthoangg/openagentd.git
cd openagentd
cp .env.example .env              # add your API key(s)

docker compose up -d              # builds and starts on http://localhost:4082
```

Or run the image directly:

```bash
docker run -e GOOGLE_API_KEY=your-key -p 4082:4082 ghcr.io/lthoangg/openagentd
```

## From source (development)

```bash
git clone https://github.com/lthoangg/openagentd.git
cd openagentd
cp .env.example .env              # add your API key(s)
uv sync                           # install Python deps
bun install --cwd web             # install frontend deps

openagentd --dev                      # backend + Vite hot-reload
# API: http://localhost:8000   Web UI: http://localhost:5173
```

Requires [uv](https://docs.astral.sh/uv/) and [Bun](https://bun.sh).

## First run

### 1. Initialize

```bash
openagentd init
```

`init` runs an interactive setup wizard:

1. **Provider** — choose from 12 LLM providers (Google Gemini, OpenAI, OpenRouter, etc.). Providers with free tiers are labelled.
2. **Model** — pick from a curated list for your provider, or type any model name.
3. **API key** — paste your key (input is hidden). OAuth-only providers (GitHub Copilot, OpenAI Codex) skip this step and prompt you to run `openagentd auth <provider>` instead.
4. **Seed config** — installs the default agent team and skills into your config directory. Existing files are never overwritten, so re-running `init` is safe.

Config is written to `~/.config/openagentd/` (XDG standard). The database and logs go to `~/.local/share/openagentd/` and `~/.local/state/openagentd/`.

### 2. Start

```bash
openagentd
```

The API and web UI start on a single port: http://localhost:4082. Database migrations run automatically.

### 3. First steps in the UI

- **Send a message** — the default lead agent (`openagentd`) is ready to chat. Start with something like "what can you do?" to explore its tools.
- **Switch agents** — click the agent name in the header to pick a different agent or spin up a team.
- **Workspace panel** — every file the agent reads, writes, or generates appears in the left panel. Click any file to preview or download it.
- **Command palette** — press `Ctrl+P` (or `Cmd+P` on macOS) to search sessions, agents, files, and actions.
- **Memory (Wiki)** — open the Wiki panel to view, edit, or delete anything the agent has remembered across sessions. The `USER.md` file at the top is always injected into every system prompt — edit it to give the agent standing context about you.

### 4. Customize your agent

Edit `~/.config/openagentd/agents/openagentd.md` to change the model, add tools, attach skills, or rewrite the system prompt. The agent picks up changes at the end of the next turn — no restart needed.

See [Configuration](configuration.md) for the full reference.

---

Database migrations run automatically on startup in production mode.

## Project layout (from source)

```
openagentd/
├── app/                    # FastAPI backend
│   ├── agent/              # Agent loop, hooks, providers, tools, teams
│   ├── api/                # Routes (thin — logic in services/)
│   ├── core/               # Config, DB, middleware, logging
│   ├── models/             # SQLModel DB schemas (chat)
│   └── services/           # Business logic, stream store, memory, dream
├── web/                    # React 19 frontend (Vite + Bun)
├── tests/                  # pytest test suite
├── seed/                   # Default config copied on first init (agents, skills, mcp.json)
└── documents/              # All documentation
```

## Next

- [CLI reference](cli.md) — every `openagentd` subcommand
- [Configuration](configuration.md) — env vars, agent YAML, providers, sandbox
- [Troubleshooting](troubleshooting.md) — common install/runtime issues
