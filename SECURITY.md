# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it privately via
GitHub's private vulnerability reporting:

- **GitHub:** [Security Advisories](https://github.com/lthoangg/openagentd/security/advisories/new)

Do **not** open a public issue for security vulnerabilities.

We aim to acknowledge reports within 48 hours and provide a fix or mitigation plan within 7 days.

---

## Trust Model

openagentd is designed as a **single-user, local-first** application. The security model assumes:

1. **The operator is the user.** The person running the backend is the same person interacting with the agent. There is no user authentication — openagentd is a single-user, on-machine tool by design.

2. **The host is trusted.** openagentd runs on your local machine and has full access to the filesystem, shell, and network within the configured sandbox boundaries.

3. **LLM providers are semi-trusted.** API keys are sent to third-party providers (Gemini, OpenAI, etc.). We do not control what providers do with your prompts. Use local models if this is a concern.

4. **Tool execution is powerful.** Agents can read/write files, execute shell commands, and browse the web. The `sandbox.workspace_root` configuration limits filesystem access, but shell commands run with the privileges of the backend process.

---

## What Is Protected

| Layer | Protection |
|-------|-----------|
| **Filesystem** | `sandbox.workspace_root` restricts file tool access. Paths outside this root are rejected. Tool output paths are relative — absolute paths are never exposed to the model. |
| **Shell** | Commands execute as the backend process user. No sandboxing beyond OS-level permissions. |
| **API keys** | Stored in `.env` (not committed). Never logged, never sent to the model. |
| **Session data** | Stored in local SQLite. No remote telemetry or data collection. |
| **SSE streams** | No authentication on SSE endpoints. Designed for localhost access only. |

---

## Deployment Assumptions

- **Do not expose the backend to the public internet** without adding authentication. The API has no auth layer — it trusts `localhost` access.
- **SQLite** database file lives under `OPENAGENTD_STATE_DIR` — ensure the directory has appropriate filesystem permissions.
- **File uploads** are validated by type and size but not scanned for malware.

---

## Out of Scope

The following are **not** security vulnerabilities in the context of openagentd's trust model:

- An agent executing a destructive shell command (the user authorized tool use)
- Reading files outside `workspace_root` via shell commands (shell has no sandbox)
- Prompt injection causing the agent to take unexpected actions (inherent LLM limitation)
- Session data visible on the local filesystem (single-user design)

---

## Supported Versions

Only the latest version on the `main` branch receives security fixes. There are no LTS releases.
