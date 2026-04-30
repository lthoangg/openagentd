---
title: System Architecture
description: C4-model system context, containers, components, in-memory SSE streaming, agent loop, SSE protocol, logging tiers.
status: stable
updated: 2026-04-21
---

# openagentd Architecture (C4 Model)

This document provides a detailed technical overview of **openagentd** using the C4 model.

## 1. System Context Diagram (Level 1)
The highest level of abstraction, showing openagentd in its environment.

```mermaid
C4Context
    title System Context Diagram for openagentd

    Person(user, "User", "A developer or power user interacting via HTTP/SSE.")
    System(openagentd, "openagentd", "On-machine AI assistant with tool-use, session persistence, and streaming.")

    System_Ext(google, "Google Gemini API", "LLM provider via Gemini Developer API.")
    System_Ext(vertex, "Vertex AI", "LLM provider via Google Cloud Vertex AI (express or normal mode).")
    System_Ext(zai, "ZAI API", "LLM provider for chat.")
    System_Ext(web, "World Wide Web", "External resources for search and fetch tools.")

    Rel(user, openagentd, "Sends messages, receives SSE stream", "HTTP/SSE")
    Rel(openagentd, google, "Sends prompts, receives completion/tools", "HTTPS/SSE")
    Rel(openagentd, vertex, "Sends prompts, receives completion/tools", "HTTPS/SSE")
    Rel(openagentd, zai, "Sends prompts, receives completion/tools", "HTTPS/SSE")
    Rel(openagentd, web, "Searches and fetches content", "HTTPS")
```

---

## 2. Container Diagram (Level 2)
Zooming into the openagentd system to see its internal containers.

```mermaid
C4Container
    title Container Diagram for openagentd

    Person(user, "User", "Browser")

    System_Boundary(openagentd_boundary, "openagentd System") {
        Container(web, "Web Frontend", "React / TypeScript / Vite / Bun", "Browser UI. Connects to backend via REST + SSE. Zustand stores, TanStack Query, streamed markdown rendering.")
        Container(api, "FastAPI Application", "Python / FastAPI / uvicorn", "Exposes REST + SSE endpoints. Handles session management, agent execution, and response streaming.")
        ContainerDb(db, "Database", "SQLite / SQLModel / Alembic", "Persists chat sessions, messages, summaries, memory facts, and memory events.")
    }

    System_Ext(llm_providers, "LLM Providers", "Gemini, Vertex AI, ZAI, OpenRouter", "HTTPS/SSE APIs")
    System_Ext(web_services, "Web Services", "Search, Fetch", "HTTPS")

    Rel(user, web, "Browser interactions", "HTTP/SSE")
    Rel(user, api, "POST /api/team/chat, GET /api/team/stream/{id}", "HTTP (direct)")
    Rel(web, api, "POST /api/team/chat, GET /api/team/stream/{id}, REST CRUD", "HTTP/SSE")
    Rel(api, db, "Reads/writes sessions and messages", "SQLModel async")
    Rel(api, llm_providers, "Makes API calls", "httpx")
    Rel(api, web_services, "Executes tools", "httpx")
```

---

## 3. Component Diagram (Level 3)
Zooming into the FastAPI Application container.

```mermaid
C4Component
    title Component Diagram for openagentd FastAPI Application

    ContainerDb(db, "Database", "SQLite")

    Container_Boundary(api_boundary, "FastAPI Application") {
        Component(routes, "API Routes", "api/routes/", "team.py, health.py, quote.py — handle HTTP requests and SSE streaming.")
        Component(agent_loader, "Agent Loader", "agent/loader.py", "Reads agents/*.md, constructs Agent instances with primary + optional fallback providers.")
        Component(agent, "Agent", "agent/agent_loop.py", "Manages the multi-turn conversational loop, tool calls, and delegates events to Hooks.")
        Component(hooks, "Agent Hooks", "agent/hooks/", "StreamingHook, StreamPublisherHook, SummarizationHook, DynamicPromptHook, SessionLogHook, TitleGenerationHook.")
        Component(checkpointer, "Checkpointer", "agent/checkpointer.py", "Checkpointer protocol + SQLiteCheckpointer. Synced at 4 points per run: after_model, tool result, summarization, run end.")
        Component(stream_store, "Stream Store", "services/stream_store.py", "In-memory turn state blob + asyncio queues per session. init_turn, push_event, attach, mark_done.")
        Component(tool_registry, "Tool Registry", "agent/tools/registry.py", "Manages available tools and JSON Schema metadata via @tool decorator.")
        Component(builtin_tools, "Builtin Tools", "agent/tools/builtin/", "filesystem (read, write, edit, ls, grep, glob, rm), shell (shell, bg), web (web_search, web_fetch), date, skill.")
        Component(permission, "Permission Service", "agent/permission.py", "Rule/Ruleset wildcard matching, last-match-wins evaluation. AutoAllowPermissionService auto-allows and fires SSE events; PermissionService blocks on asyncio.Future until user replies.")
        Component(provider, "LLM Provider", "agent/providers/", "GoogleGenAIProvider, VertexAIProvider, ZAIProvider, OpenRouterProvider, … — all implement LLMProviderBase. agent/providers/factory.py:build_provider dispatches a 'provider:model' string with one match statement.")
        Component(chat_service, "Chat Service", "services/chat_service.py", "Sessions, messages, and team-history aggregation. Owns list/delete/get_team_history; get_messages_for_llm returns visible + summary context.")
        Component(quote_service, "Quote Service", "services/quote_service.py", "Fetches and caches daily quote from API Ninjas (free tier: 3000 calls/month).")
        Component(models, "Models", "models/", "SQLModel database schemas: ChatSession, SessionMessage.")
        Component(schemas, "Schemas", "agent/schemas/", "Pydantic models: chat.py, agent.py, events.py (SSE wire types).")
         Component(teams, "Agent Teams", "agent/mode/team/", "AgentTeam, TeamLead, TeamMember, TeamMailbox, team_message tool for peer messaging. Refer to app/agent/AGENTS.md for details.")
        Component(logging, "Logging", "core/logging_config.py", "Loguru-based: app logs to {OPENAGENTD_STATE_DIR}/logs/app/, per-session logs to {OPENAGENTD_STATE_DIR}/logs/sessions/{id}/.")
    }

    System_Ext(gemini, "Gemini / Vertex AI")
    System_Ext(zai, "ZAI Provider")

    Rel(routes, agent_loader, "Gets loaded agent config")
    Rel(routes, agent, "Runs agent turns via agent.run()")
    Rel(agent, hooks, "Fires lifecycle events")
    Rel(agent, provider, "Streams completions via LLMProviderBase")
    Rel(agent, tool_registry, "Fetches tool definitions, executes tools")
    Rel(checkpointer, db, "Persists messages and tool results via chat_service")
    Rel(routes, chat_service, "Load/save messages")
    Rel(provider, gemini, "GoogleGenAIProvider / VertexAIProvider")
    Rel(provider, zai, "ZAIProvider")
```

---

## 4. In-Memory SSE Streaming Architecture

### Overview

Every chat turn is backed by an in-memory state blob + asyncio fan-out queues (one per SSE client). This enables:
- **Fire-and-forget POST**: `POST /api/team/chat` returns 202 immediately, agent runs in background.
- **Mid-turn reconnect**: clients that disconnect and reconnect receive buffered content.
- **Multi-client streaming**: multiple tabs can watch the same session simultaneously (single-process).

### Data Layout (per session_id)

`memory_stream_store._turns[session_id]` holds a `_TurnState` instance that accumulates per-agent content, thinking, tool calls, statuses, and subscriber queues (see `app/services/memory_stream_store.py:36`).

`content` and `thinking` are **per-agent buckets** — replay re-emits each bucket with the correct `agent` field so mid-turn refreshes in a team session route tokens to the right agent's stream. `agent_statuses` is a latest-wins map so reconnecting clients immediately know which agents are `working` / `available` / `error`.

The state blob holds **only unpersisted live content**. After `checkpointer.sync()` writes assistant/tool rows to the DB, `stream_store.commit_agent_content(session_id, agent)` drops `content[agent]`, `thinking[agent]`, and every `tool_calls` entry whose `agent` field matches — otherwise a refresh between sync and the team-wide `mark_done()` would render the same block twice. Inbox messages are **not** stored in the blob — `_persist_inbox` writes the `HumanMessage` row before emitting the `inbox` SSE event, so replay is DB-backed.

### Turn Lifecycle

1. **`init_turn(session_id)`** — called synchronously in POST handler before spawning the background task. Creates `_TurnState`, sets `is_streaming=True`. Eliminates producer/consumer race condition.
2. **`push_event(session_id, envelope: StreamEnvelope)`** — called for every SSE event. The envelope is a typed Pydantic wrapper `{event: str, data: dict}` (see `app/services/stream_envelope.py`). Updates state blob and fans out `envelope.to_wire()` to all subscriber queues.
3. **`attach(session_id)`** — called by `GET /api/team/{session_id}/stream`. Subscribe-before-read two-phase protocol:
   - If `is_streaming=False` → return immediately (DB is authoritative).
   - Register a subscriber `asyncio.Queue` BEFORE replaying state (closes the gap window).
   - Replay accumulated state as synthetic events in order: `agent_status` (per agent) → `thinking` (per agent) → `tool_call` / `tool_start` / `tool_end` → `message` (per agent).
   - Yield live events from the queue until sentinel arrives.
4. **`mark_done(session_id)`** — sets `is_streaming=False`, pushes sentinel to all queues. Called after the turn completes.

### SSE Wire Format

Events are emitted by `sse_starlette` as:
```
event: <type>\n
data: <json>\n
\n
```

The `type` field inside the JSON body mirrors the SSE `event:` line. Both must be used.

### SSE Event Protocol

| Event | Direction | Payload fields |
|-------|-----------|---------------|
| `session` | server→client | `session_id` |
| `thinking` | server→client | `agent`, `text` |
| `message` | server→client | `agent`, `text` |
| `tool_call` | server→client | `agent`, `tool_call_id`, `name` — first delta, no args yet |
| `tool_start` | server→client | `agent`, `tool_call_id`, `name`, `arguments` — full args, execution beginning |
| `tool_end` | server→client | `agent`, `tool_call_id`, `name`, `result` — execution done |
| `usage` | server→client | `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens`, `thoughts_tokens` |
| `rate_limit` | server→client | `retry_after`, `attempt`, `max_attempts` |
| `error` | server→client | `message` |
| `done` | server→client | — |
| `agent_status` | server→client | `agent`, `status` (`working`\|`available`\|`error`) — team only |
| `permission_asked` | server→client | `request_id`, `session_id`, `tool`, `patterns` — agent requesting approval before executing a tool |
| `permission_replied` | server→client | `request_id`, `session_id`, `reply` (`once`\|`always`\|`reject`) — permission request resolved |

### 3-Phase Tool Event Lifecycle

```
tool_call   ← fired from model streaming delta (first name appearance)
               → frontend shows spinner card immediately, no args
tool_start  ← fired from wrap_tool_call BEFORE execution (full args assembled)
               → frontend fills in args
tool_end    ← fired from wrap_tool_call AFTER execution
               → frontend marks done, shows result
```

`tool_call_id` is the LLM-assigned call ID (e.g. `call_f70e3244...`). It flows through all three events so the frontend can match them reliably, even when the same tool is called multiple times in parallel.

**Critical**: `tool_end` must use the `tool_call_id` registered at `tool_call` time (from the streaming delta), NOT from the assembled `ToolCall` buffer — the buffer may have wrong IDs when providers send parallel calls with the same `index`.

---

## 5. Agent Architecture

The agent engine lives entirely under `app/agent/`. For detailed documentation see [`documents/docs/agent/`](agent/):

| Doc | Covers |
|-----|--------|
| [`loop.md`](agent/loop.md) | Reasoning loop, retry logic, tool buffering, interrupt |
| [`hooks.md`](agent/hooks.md) | Hook lifecycle, built-in hooks, checkpointer, custom hooks |
| [`context.md`](agent/context.md) | RunContext, AgentState, message types, system prompt injection |
| [`tools.md`](agent/tools.md) | @tool decorator, Tool class, built-in tools, registration |
| [`teams.md`](agent/teams.md) | Multi-agent teams, mailbox, team_message peer messaging |
| [`summarization.md`](agent/summarization.md) | Rolling-window context compression |

### Request flow (sequence diagram)

```mermaid
sequenceDiagram
    participant User
    participant TeamRoute
    participant Agent
    participant Provider
    participant Tools
    participant DB

    User->>TeamRoute: POST /api/team/chat {session_id, message}
    TeamRoute->>DB: Load session messages (get_messages_for_llm)
    TeamRoute->>Agent: agent.run(messages, hooks=[StreamingHook, SessionLogHook], checkpointer=SQLiteCheckpointer)
    Agent->>Provider: Stream completion
    Provider-->>Agent: Thinking + ToolCall(date)
    Agent->>Agent: fire on_model_delta → StreamingHook pushes SSE thinking event
    Agent->>Tools: Execute date() in parallel via wrap_tool_call hook chain
    Tools-->>Agent: "2026-04-02..."
    Agent->>DB: checkpointer.sync() saves AssistantMsg + ToolMsg (skips empty AssistantMsg)
    Agent->>Provider: Next completion (with Tool result)
    Provider-->>Agent: Final Answer
    Agent->>Agent: fire after_model → StreamingHook pushes SSE text delta
    TeamRoute->>User: SSE stream (done event)
```

---

## 6. Logging architecture

Two-tier logging (application-wide + per-session JSONL via `SessionLogHook`)
under `{OPENAGENTD_STATE_DIR}/logs/`. See [`logging.md`](./logging.md) for the
directory layout, event catalogue, configuration knobs, and console-output
format.

---

## 7. Security & trust model

openagentd is a **single-user, local-first** application. The security model assumes:

- **The operator is the user.** No authentication layer — the backend trusts localhost access.
- **The host is trusted.** The process has full access to the filesystem, shell, and network within configured sandbox boundaries.
- **LLM providers are semi-trusted.** API keys are sent to third-party providers (Gemini, etc.). Use local models if this is a concern.
- **Tool execution is powerful.** Agents can read/write files, run shell commands, and browse the web. `sandbox.workspace_root` limits file tool access, but shell commands run with the privileges of the backend process.

**Do not expose the backend to the public internet** without adding an authentication layer first.

| Layer | Protection |
|-------|-----------|
| Filesystem | `sandbox.workspace_root` restricts file tool access; paths outside are rejected. |
| Shell | Commands run as the backend process user — no additional sandboxing. |
| API keys | Stored in `.env` (not committed). Never logged or sent to the model. |
| Session data | Local SQLite only. No remote telemetry or data collection. |
| SSE streams | No auth on SSE endpoints — localhost access only by design. |

The following are **not** considered vulnerabilities given this trust model:

- An agent executing a destructive shell command (user authorized tool use)
- Reading files outside `workspace_root` via shell (shell has no sandbox)
- Prompt injection causing unexpected agent actions (inherent LLM limitation)
- Session data visible on the local filesystem (single-user design)
