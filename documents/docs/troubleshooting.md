# Troubleshooting

Common install and runtime issues. Run `openagentd doctor` first — it surfaces most of these automatically.

## `command not found: openagentd` after pip install

Make sure your Python scripts directory is on `PATH`. Try `python -m app.cli` as a fallback, or install with `uv tool install openagentd` (which manages PATH for you).

## `command not found: uv`

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## `command not found: bun` (development only)

Install Bun:

```bash
curl -fsSL https://bun.sh/install | bash
```

Bun is only needed for development. Production installs (`pip install` / Docker) don't require it.

## Server starts but the web UI shows a blank page

- If running from source without `make build-web`, use `openagentd --dev` which starts the Vite dev server separately.
- If using `openagentd` (production mode), run `make build-web` first to bundle the frontend.

## `GOOGLE_API_KEY not set` or similar provider errors

Copy `.env.example` to the correct location (see [Configuration](configuration.md)) and add your API key. At least one LLM provider key is required.

## Gemini `400 INVALID_ARGUMENT` — unknown field in function declarations

The Gemini API rejects JSON Schema fields it doesn't recognise (`discriminator`, `const`, `exclusiveMinimum`, `additionalProperties`, etc.) in tool schemas. `GeminiProviderBase._sanitize_schema()` strips these automatically — if you see this error it likely means a tool schema contains a new unsupported field. Add it to `_UNSUPPORTED_SCHEMA_KEYS` in `app/agent/providers/googlegenai/googlegenai.py`. See [Gemini schema sanitization](agent/tools.md#gemini-schema-sanitization) for the full list.

## SQLite `database is locked` errors

Usually means two server instances are running. Run `openagentd stop`, then `openagentd`.

## Docker: `permission denied` on `/data`

The container runs as a non-root user. Make sure the volume mount is writable:

```bash
docker compose down -v && docker compose up -d
```

## Related

- [Install](install.md)
- [CLI reference](cli.md)
- [Configuration](configuration.md)
