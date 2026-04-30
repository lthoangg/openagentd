---
name: plugin-installer
description: >-
  Install a user plugin from a URL into `{OPENAGENTD_CONFIG_DIR}/plugins/`.
  Use when the user provides a URL and asks to add / install a plugin.
---

# Plugin Installer

A plugin is a single `.py` file in `{OPENAGENTD_CONFIG_DIR}/plugins/` that
hooks into the agent loop. Two contracts are valid:

**Functional** — `async def plugin()` returning an event dict:

```python
async def plugin():
    async def before(input, output):
        # input: {tool, session_id, run_id, agent_name, call_id}
        # output: {args}  ← mutate in place to rewrite tool args
        # raise to abort: result becomes "Error: <message>"
        ...

    async def after(input, output):
        # input: {tool, session_id, run_id, agent_name, call_id, args}
        # output: {output}  ← mutate to rewrite the result the LLM sees
        ...

    return {
        "tool.before": before,
        "tool.after": after,
        "applies_to": lambda agent_name, role: True,  # optional
    }
```

**Class-based** — `class Plugin(BaseAgentHook)` for the full hook surface
(`wrap_model_call`, `before_agent`, `on_rate_limit`, …).

Files prefixed with `_` are skipped. Roles are `lead` (team orchestrator),
`member` (team worker), `agent` (direct callers).

## Install from URL

1. **`web_fetch`** the URL as-is. If the response is HTML (GitHub `blob`
   URL), ask for the raw URL and stop.
2. **Validate** the body contains `async def plugin(` or `class Plugin(`.
   If not, refuse — it's not a plugin.
3. **Filename** = URL basename. Must end in `.py`, no leading `_`.
4. **Collision** → read existing, show diff, confirm before overwrite.
5. **Show** the first ~40 lines of the fetched content before writing.
   The user is installing in-process Python — let them see it.
6. **Write** to `{OPENAGENTD_CONFIG_DIR}/plugins/<name>.py`.
7. **Tell the user to restart openagentd.** No hot reload — hooks are cached
   per `(Agent, role)` on first call.

## Other intents

| User says           | Do                                                       |
| ------------------- | -------------------------------------------------------- |
| "list plugins"      | `ls {OPENAGENTD_CONFIG_DIR}/plugins/`                        |
| "remove X"          | Delete or rename `…/plugins/X.py` to `_X.py`             |
| "write me a plugin" | Decline. LLM-authored in-process Python isn't worth it.  |

## Rules

- **No URL → no install.** Authoring is a developer task.
- **One file, no dependencies.** Refuse multi-file packages.
- **Never silently overwrite.** Always diff and confirm.

## Failure modes

- **HTML instead of Python** → user pasted a `blob` URL; ask for raw.
- **Validation fails** → not a plugin; show first 200 chars and stop.
- **Plugin missing after restart** → check openagentd log for
  `plugin_load_failed` (the loader skips broken files defensively).
