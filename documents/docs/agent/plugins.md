---
title: User Plugins
description: User-authored Python plugins that hook into the agent loop without modifying the codebase.
status: stable
updated: 2026-04-27
---

# User Plugins

**Source:** `app/agent/plugins/` · **Example:** [`.openagentd/config/plugins/example.py`](../../../.openagentd/config/plugins/example.py)

Drop a `.py` file into `{OPENAGENTD_CONFIG_DIR}/plugins/` (default `.openagentd/config/plugins/`) to hook into the agent loop without touching the codebase. The loader discovers plugins at agent-build time and adapts them into [`BaseAgentHook`](hooks.md) instances.

Set `OPENAGENTD_PLUGINS_DIRS` (colon-separated) to point elsewhere. Files prefixed with `_` are skipped — useful for helper modules.

---

## Two contracts

### Functional — `async def plugin()` returning an event dict

Best for tool-arg/result rewrites. See [`example.py`](../../../.openagentd/config/plugins/example.py) for a 40-line working plugin that rewrites `shell({"command": "hello"})` into `echo hello`.

```python
async def plugin():
    async def before(input, output):
        # mutate output["args"] in place; raise to abort with the message as result
        ...

    async def after(input, output):
        # mutate output["output"] to rewrite the result the LLM sees
        ...

    return {
        "tool.before": before,
        "tool.after": after,
        "applies_to": lambda agent_name, role: True,  # optional
    }
```

**Events** (TypedDict shapes live in [`app/agent/plugins/events.py`](../../../app/agent/plugins/events.py)):

| Event         | Mutable output | Failure mode                                                |
| ------------- | -------------- | ----------------------------------------------------------- |
| `tool.before` | `args`         | Raise → `"Error: <message>"` returned, executor not called. |
| `tool.after`  | `output`       | Logged; original tool result preserved.                     |

### Class-based — `class Plugin(BaseAgentHook)`

Use when you need the full hook surface (`wrap_model_call`, `before_agent`, `on_rate_limit`, …). Subclass [`BaseAgentHook`](hooks.md) and expose it as `Plugin`. Configuration: import `app.core.config.settings` directly.

---

## `applies_to(agent_name, role)`

Optional filter run once per agent at load time. Roles: `lead` (team orchestrator), `member` (team worker), `agent` (direct `Agent.run()` callers). Propagated via `app.agent.plugins.role` contextvar — set by the team runner, so `Agent.run()` takes no role parameter.

---

## Loading & isolation

- **Lazy & cached** per `(Agent, role)`. Restart the process to pick up edits — no hot reload.
- **Isolated failures:** import error → `plugin_load_failed` log, file skipped, others continue. `applies_to` raise → treated as not applicable. Class-hook errors → caught by `_safe_invoke_hooks()` (see [`hooks.md`](hooks.md)).
- **Order:** user plugins run after `Agent.hooks` and per-call `hooks=` — built-ins win.

---

## See also

- [`hooks.md`](hooks.md) — full hook protocol and lifecycle.
- [`loop.md`](loop.md) — where each event fires in the agent loop.
- [`example.py`](../../../.openagentd/config/plugins/example.py) — minimal functional plugin.
