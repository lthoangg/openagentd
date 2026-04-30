"""GitHub Copilot provider schemas.

The chat completions wire format is OpenAI-compatible — we reuse
``app.agent.providers.openai.schemas`` for request/response types.

Authentication uses the GitHub OAuth token directly (no token exchange).
OAuth credential storage lives in ``app.cli.commands.auth``.
"""
