---
name: mcp-installer
description: >-
  Install, update, remove, or restart Model Context Protocol (MCP) servers
  in `{OPENAGENTD_CONFIG_DIR}/mcp.json`. Use when the user asks to add / remove /
  list / restart an MCP, or to enable a server like filesystem, github,
  postgres, puppeteer, brave-search.
---

# MCP Installer

`{OPENAGENTD_CONFIG_DIR}/mcp.json` is the source of truth. The agent edits
it directly with `read` / `edit` / `write`, then asks the running daemon
to re-read it via one HTTP call:

```bash
curl -sS -X POST http://localhost:4082/api/mcp/apply
```

The daemon validates the file (Pydantic schema), reconciles only the
runners that changed, and returns a JSON envelope with each server's
state. Other servers, the running team, and any in-flight turn are
**not** disrupted.

No client-side validation step exists or is needed — the daemon is the
sole authority on schema correctness, and its 422 response carries the
exact error message.

## When to use

| User intent                                  | Action                                                  |
| -------------------------------------------- | ------------------------------------------------------- |
| Install / update / remove / disable a server | Edit `mcp.json`, `apply`, **then wire into an agent**   |
| Restart one server (no config change)        | `POST /api/mcp/servers/<name>/restart`                  |
| List servers (config + state)                | `GET /api/mcp/servers`                                  |
| Inspect one server                           | `GET /api/mcp/servers/<name>`                           |
| Attach server's tools to an agent            | **Delegate to `self-healing`** — it owns agent files    |

## Workflow — install / update / remove

1. **Read** `mcp.json` (create with `{"servers": {}}` if missing).

2. **Confirm secrets exist** before installing servers that need them.
   Use the same `printenv`/`head -c 4` pattern as `self-healing`:

   ```bash
   printenv GITHUB_PERSONAL_ACCESS_TOKEN | head -c 4
   ```

   Empty output → tell the user to add it to
   `{OPENAGENTD_CONFIG_DIR}/.env` and restart openagentd. Don't
   install a server you know will fail.

3. **Expand `~` and relative paths** before writing them to args. MCP
   servers are spawned by the daemon under its own cwd; `~` won't
   expand inside the JSON. Use `realpath`:

   ```bash
   realpath ~/Documents          # → /Users/<you>/Documents
   ```

   Pass the absolute path into `args`. Quote any path containing
   spaces (the JSON encoder takes care of escaping; you just need
   the right value).

4. **For removals**, first
   `rg '<name>' {OPENAGENTD_CONFIG_DIR}/agents/`. If any agent has
   the server in its `mcp:` list or any `mcp_<name>_*` entry in
   `tools:`, **delegate to `self-healing`** to strip those references
   *before* `apply`. Otherwise the next-turn rebuild logs
   `agent_config_refresh_failed` and the agent keeps stale config.

5. **Show the planned edit** as a fenced ```json block before
   writing, unless the user was already explicit.

6. **Edit** `mcp.json` with `edit`. Server name regex
   `^[a-zA-Z][a-zA-Z0-9_-]*$`; immutable (rename = remove + add).
   Don't inline secrets — reference env vars only.

7. **Apply**:

   ```bash
   curl -sS -X POST -w '\nHTTP %{http_code}\n' \
     http://localhost:4082/api/mcp/apply
   ```

   - **HTTP 200** with JSON body: success. Inspect the body's
     `servers[].state` field — `ready` means the runner is up,
     `errored` means the runner failed (look at `error`).
   - **HTTP 422** with `{"detail": "..."}`: file on disk failed
     schema validation. Show the detail verbatim, fix `mcp.json`,
     retry. Common causes: trailing comma, `"true"` instead of
     `true`, invalid server-name characters.
   - **Connection refused / timeout**: daemon isn't on port 4082.
     This shouldn't happen during an agent turn — surface the raw
     error and stop.

8. **Verify from the response body** — don't issue a second `curl`.
   You already have the truth.

9. **Wire into an agent.** Installing alone does NOT make the tools
   callable. **Delegate to `skill("self-healing")`** to add the
   server name to the target agent's `mcp:` or `tools:` list.
   `self-healing` owns the agent-file workflow.

## Other endpoints

```bash
# List every configured server with current state.
curl -sS http://localhost:4082/api/mcp/servers | jq

# Inspect one server (state + tool_names + last error if any).
curl -sS http://localhost:4082/api/mcp/servers/<name> | jq

# Restart one runner without touching mcp.json.
curl -sS -X POST http://localhost:4082/api/mcp/servers/<name>/restart | jq
```

`/restart` is for "the server crashed, give it another life" — it
doesn't re-read `mcp.json`. For config changes, always go through
`/apply`.

## Config shapes

```json
{
  "servers": {
    "filesystem": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/Documents"],
      "env": {},
      "enabled": true
    },
    "my-remote": {
      "transport": "http",
      "url": "https://mcp.example.com/v1",
      "headers": {"Authorization": "Bearer ${MY_REMOTE_TOKEN}"},
      "enabled": true
    }
  }
}
```

`enabled: false` keeps the entry but contributes no tools (state
`stopped`). Env-var substitution in `headers`/`env` uses
`${VAR_NAME}` syntax — the daemon resolves at spawn time.

## Common servers

| Name         | Command + args                                                    |
| ------------ | ----------------------------------------------------------------- |
| filesystem   | `npx -y @modelcontextprotocol/server-filesystem <abs-path>`         |
| github       | `npx -y @modelcontextprotocol/server-github` (needs token env)      |
| brave-search | `npx -y @modelcontextprotocol/server-brave-search` (needs key env)  |
| postgres     | `npx -y @modelcontextprotocol/server-postgres <conn-string>`        |
| puppeteer    | `npx -y @modelcontextprotocol/server-puppeteer`                     |
| sqlite       | `uvx mcp-server-sqlite --db-path <abs-path>`                        |

Verify the package name with the user — npm names drift.

## Failure modes

- **HTTP 422 from `/apply`** → schema disagreement. Show `detail`
  verbatim. Common: trailing comma, wrong type, invalid server name.
- **Server in `errored` after `/apply`** → show the `error` field;
  suggest the obvious fix (missing npm package, wrong path, missing
  env var). Don't retry blindly.
- **`agent_config_refresh_failed` after `/apply`** (next turn's
  logs) → an agent's `tools:` list references a tool that no longer
  exists. `rg 'mcp_' {OPENAGENTD_CONFIG_DIR}/agents/` then delegate
  to `self-healing`. The agent keeps its previous config until fixed.
- **Connection refused** → daemon down. The agent itself runs inside
  the daemon, so this means something is very wrong. Surface the
  error and stop; don't try to start it.

A failing MCP server does NOT block other servers, the team, or any
in-flight turn — tell the user that, they often assume the worst.
