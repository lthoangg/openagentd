# Comparison

How openagentd positions against the other notable open-source self-hosted agent
projects. All four are MIT/Apache and self-hosted; the differences are in **what
they're for** and **how you drive them**.

> **A note on accuracy.** Rows in our column are sourced from this repo. Rows in
> competitor columns are sourced from each project's public README and docs as of
> the date this file was last updated. If you spot something wrong, please open
> a PR — we'd rather be corrected than ship an inaccurate comparison.

## At a glance

|                       | **openagentd**                       | **[opencode](https://opencode.ai)**     | **[openclaw](https://openclaw.ai)**             | **[hermes-agent](https://hermes-agent.nousresearch.com)** |
|-----------------------|--------------------------------------|-----------------------------------------|-------------------------------------------------|-----------------------------------------------------------|
| **Repo**              | `lthoangg/openagentd`                | `anomalyco/opencode`                    | `openclaw/openclaw`                             | `NousResearch/hermes-agent`                               |
| **License**           | Apache 2.0                           | MIT                                     | MIT                                             | MIT                                                       |
| **Language**          | Python (FastAPI) + React             | TypeScript                              | TypeScript                                      | Python (uv)                                               |
| **Niche**             | Personal AI OS with a cockpit UI     | AI coding agent for the terminal        | Personal assistant in your messaging apps       | Self-improving autonomous server agent                    |
| **Primary surface**   | Web cockpit + REST/SSE API           | TUI + IDE extensions + desktop (beta)   | WhatsApp / Telegram / Slack / Discord / iMessage / Signal | Telegram / Discord / Slack / WhatsApp / Email + CLI       |

## Capability matrix

|                                | openagentd                                                                                                                | opencode                                                | openclaw                                            | hermes-agent                                            |
|--------------------------------|---------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------|-----------------------------------------------------|---------------------------------------------------------|
| **First-party UI**             | Full web app: chat, command palette, tool-call inspector, memory panel, scheduler, split-grid team view, telemetry dashboard | Terminal UI; web/desktop secondary                      | None — chat bubbles in your existing apps          | None — channel-native + terminal                        |
| **Real-time UX**               | SSE with reconnect-safe replay (close tab → reopen → stream resumes)                                                      | Terminal streaming                                      | Per-message in your messaging app                   | Per-message in your messaging app                       |
| **Multi-agent**                | Lead + worker teams, async inter-agent mailbox, `team_message` delegation tool, per-agent SSE pane                        | `build` / `plan` agents + `@general` subagent           | Multi-agent routing per channel/peer                | Isolated subagents with own terminals + Python RPC      |
| **Built-in tools**             | filesystem, shell + bg, web search/fetch, image gen + edit, video gen, scheduler, todos, skills, MCP                      | shell, file edit, glob, grep, web fetch/search, LSP     | browser, canvas, sessions, cron, channel actions   | web, browser, terminal, vision, image gen, TTS, NL cron |
| **Image / video gen**          | Yes — multi-provider images + edit; native video                                                                          | None native                                             | Via plugin providers                                | Image gen; no native video                              |
| **MCP servers**                | Hot-reload via `POST /api/mcp/apply`                                                                                      | Local + remote MCP, OAuth, per-agent scoping            | Bundled MCP via plugin keys                         | Hot-reload via `/reload-mcp`                            |
| **Skills system**              | Markdown SKILL.md, lazy-loaded, hot-reload on mtime, token substitution                                                   | SKILL.md compatible                                     | Markdown skills, ClawHub registry                   | Markdown skills + auto-creates new skills from experience |
| **Self-modification**          | `self-healing` skill — agent edits its own `.md` (model, tools, skills, MCP)                                              | None documented                                         | Gateway config patching at runtime                  | Modifies persona file; auto-improves skills from use    |
| **Memory**                     | Three-tier markdown (system / topics / notes) + editable in UI                                                            | Session resume + `/compact`; no cross-session knowledge | Per-session persistence, memory tools               | MEMORY.md + USER.md + FTS5 cross-session search         |
| **Summarization**              | Per-agent rolling-window with configurable summarizer model                                                               | `/compact` command                                      | Implicit per-session                                | `/compress`, `/usage` commands                          |
| **Provider matrix**            | Gemini, Vertex, OpenAI, OpenRouter, ZAI, NIM, xAI, DeepSeek, Copilot OAuth, Codex OAuth, local proxies, fallback chains   | 75+ via Models.dev / AI SDK                             | 35+ providers, OAuth subscriptions                  | Nous Portal, OpenRouter, NIM, OpenAI, etc.              |
| **Sandbox**                    | Path denylist + permission system (allow/deny/ask, wildcard rules)                                                        | Granular per-tool permissions, glob patterns            | Docker / SSH / OpenShell backends                   | Multiple backends: local, Docker, SSH, Modal, Daytona   |
| **Plugins**                    | Python plugins with `tool.before` / `tool.after` hooks, per-agent filtering                                               | TypeScript plugins via SDK                              | Channel/provider/tool/skill plugins                 | Python plugins (memory providers, orchestrators)        |
| **Telemetry**                  | OpenTelemetry built-in; DuckDB-backed `/telemetry` dashboard; optional OTLP export                                        | None native                                             | Logging-only                                        | Trajectory export for RL training                       |
| **Logging**                    | Two-tier loguru: app log + per-session JSONL + transcript                                                                 | Session export, structured plugin logging               | App + session logs                                  | Session SQLite + FTS5                                   |
| **Hot-reload**                 | Drift detection at end of every turn (agent `.md`, `mcp.json`, `SKILL.md`)                                                | Restart for config                                      | Gateway config patching                             | `/reload-mcp` for MCP                                   |
| **Programmatic access**        | First-class — documented REST + SSE drives the bundled UI                                                                 | Client/server protocol                                  | Gateway/RPC, channel-shaped                         | Gateway, channel-shaped                                 |
| **Embed in your app**          | Yes — hit the API or embed the wheel-bundled web UI                                                                       | Possible via client/server protocol                     | Channel-shaped, not app-shaped                      | Channel-shaped, not app-shaped                          |
| **Install**                    | `uv tool install openagentd`                                                                                              | `npm i -g opencode-ai` / brew / scoop / curl            | `npm install -g openclaw@latest`                    | `curl ... install.sh \| bash` (uv-based)                |

## Where openagentd fits

openagentd is a *personal AI assistant OS with a real web cockpit*: a
long-running on-machine multi-agent system you drive from a polished web app,
with batteries-included tools, persistent memory, lead+worker teams, and a
documented HTTP/SSE API you can build your own product on top of.

Pick openagentd when you want one polished local app where you drive a team of
agents and watch what they're doing — not a terminal coding assistant, not a
chat-app integration, not an unattended server agent.
