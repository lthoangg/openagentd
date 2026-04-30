---
title: Agent Engine Architecture
description: Module layout and entry points for LLM execution, context management, and multi-agent coordination.
status: stable
updated: 2026-04-21
---

# Agent Engine

Everything under `app/agent/` that drives LLM execution, context management, tool use, and multi-agent coordination.

## Module layout

```
app/agent/
├── agent_loop.py       # Agent class — main reasoning loop
├── state.py            # RunContext, ModelRequest, AgentState (capabilities, tool_names), build_tool_chain
├── multimodal.py       # build_parts_from_metas() — attachment hydration for user uploads
├── checkpointer.py     # Checkpointer protocol + SQLiteCheckpointer
├── errors.py           # Domain exceptions
├── sandbox.py          # SandboxConfig, get_sandbox, set_sandbox (context var)
├── sandbox_config.py   # sandbox.yaml load/save — user-defined deny-glob patterns
├── tool_id_resolver.py # FIFO tool_call_id resolution for streaming
├── loader.py           # Loads agents/*.md — agent factory
├── drift.py            # ConfigStamp + stamp_agent_files / detect_drift (leaf module)
├── hooks/              # Hook lifecycle API + built-in hooks
├── providers/          # LLM provider adapters + capability detection
│   ├── factory.py          # build_provider("provider:model") — one match over the prefix
│   ├── capabilities.py     # Dataclasses, defaults, prefix fallbacks, YAML loader
│   └── capabilities.yaml   # Exact per-model capability overrides
├── schemas/            # Pydantic wire types (messages, events)
├── tools/              # Tool registry (@tool decorator) + built-ins
│   └── builtin/filesystem/handlers.py  # Multimodal file handlers (image, document, text)
└── mode/

    └── team/           # AgentTeam, TeamLead, TeamMember, mailbox, tools
```

## Documents

| Document | What it covers |
|----------|---------------|
| [loop.md](./loop.md) | Reasoning loop, iteration lifecycle, retry, tool dispatch |
| [hooks.md](./hooks.md) | Hook protocol, all built-in hooks, custom hook patterns |
| [plugins.md](./plugins.md) | User-authored plugins — drop-in `.py` files that wrap tools and hook into the loop |
| [tools.md](./tools.md) | Tool registry, `@tool` decorator, built-ins, injection paths |
| [teams.md](./teams.md) | Multi-agent coordination — team, mailbox, task board, protocol, live-config drift detection |
| [context.md](./context.md) | AgentState, RunContext, system prompt injection, metadata |
| [summarization.md](./summarization.md) | Rolling-window context compression |
| [memory.md](./memory.md) | Wiki memory — notes, dream synthesis, USER.md injection |

## Entry points

| Use case | Entry point |
|----------|------------|
| Single-agent chat | `api/routes/chat.py` → `agent.run(messages, config=config)` |
| Multi-agent team | `api/routes/team.py` → `team.handle_user_message(content, session_id)` |
| Standalone / test | Construct `Agent` directly — see [context.md](./context.md) |
