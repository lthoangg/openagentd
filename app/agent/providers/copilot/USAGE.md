# GitHub Copilot — Usage & Billing

Copilot bills **per request** (not per token). One user prompt = one premium request × model multiplier.

Only **your prompts** count — tool calls and autonomous agent actions do **not** consume premium requests.

Source: https://docs.github.com/en/copilot/managing-copilot/monitoring-usage-and-entitlements/about-premium-requests

## Plan allowances

| Plan             | Premium requests/month | Included models (unlimited)      |
| ---------------- | ---------------------- | -------------------------------- |
| Copilot Free     | 50                     | —                                |
| Copilot Student  | 300                    | GPT-5 mini, GPT-4.1, GPT-4o     |
| Copilot Pro      | 300                    | GPT-5 mini, GPT-4.1, GPT-4o     |
| Copilot Pro+     | 1,500                  | GPT-5 mini, GPT-4.1, GPT-4o     |
| Copilot Business | 300/user               | GPT-5 mini, GPT-4.1, GPT-4o     |
| Copilot Enterprise | 1,000/user           | GPT-5 mini, GPT-4.1, GPT-4o     |

Additional premium requests: $0.04/request (not available on Free plan).

## Model multipliers (paid plans)

| Model                        | Multiplier | Prompts from 300 PRs |
| ---------------------------- | ---------- | -------------------- |
| GPT-5 mini                   | **0** (free)   | **Unlimited**            |
| GPT-4.1                      | **0** (free)   | **Unlimited**            |
| GPT-4o                       | **0** (free)   | **Unlimited**            |
| Grok Code Fast 1             | 0.25       | 1,200                |
| GPT-5.4 mini                 | 0.33       | ~909                 |
| Claude Haiku 4.5             | 0.33       | ~909                 |
| Gemini 3 Flash               | 0.33       | ~909                 |
| Claude Sonnet 4 / 4.5 / 4.6 | 1          | 300                  |
| GPT-5.1 / 5.2 / 5.4         | 1          | 300                  |
| GPT-5.2-Codex / 5.3-Codex   | 1          | 300                  |
| Gemini 2.5 Pro / 3.1 Pro    | 1          | 300                  |
| Claude Opus 4.5 / 4.6       | 3          | 100                  |
| Claude Opus 4.6 (fast mode)  | 30         | 10                   |

## Agent loop cost estimate

In openagentd's agent loop, each **LLM call** counts as a prompt — not just the user's initial message. A single user message that triggers N tool calls = ~(N+1) LLM calls.

Example with 300 premium requests/month:

| Model            | Multiplier | Effective LLM calls | Sessions (~6 calls each) |
| ---------------- | ---------- | ------------------- | ------------------------ |
| GPT-5 mini       | 0          | Unlimited           | Unlimited                |
| Grok Code Fast 1 | 0.25       | 1,200               | ~200                     |
| GPT-5.4 mini     | 0.33       | ~909                | ~151                     |
| Claude Sonnet 4  | 1          | 300                 | ~50                      |
| Claude Opus 4.5  | 3          | 100                 | ~16                      |

## Recommended models for openagentd

- **Daily driver**: `copilot:gpt-5-mini` — unlimited, free on paid plans
- **Fast + cheap**: `copilot:grok-code-fast-1` — 0.25x, good for heavy tool-calling agents
- **Best premium value**: `copilot:gpt-5.4-mini` — 0.33x, newer model
- **Best quality**: `copilot:claude-sonnet-4` — 1x, strong reasoning

## Reasoning / thinking support

Set `thinking_level` in the agent's `.md` frontmatter to enable reasoning. Supported values: `low`, `medium`, `high`.

```yaml
---
name: assistant
model: copilot:gpt-5.4-mini
thinking_level: low
---
```

### How it maps to the API

| Endpoint           | Request param                            | Response                              |
| ------------------ | ---------------------------------------- | ------------------------------------- |
| `/chat/completions` | `reasoning_effort: "low"`                | Hidden reasoning tokens (internal)    |
| `/responses`        | `reasoning: {effort: "low", summary: "auto"}` | Streamed reasoning summary + tokens   |

### Endpoint behavior differences

- **`/chat/completions`** (gpt-5-mini, etc.): Reasoning happens internally. Tokens are consumed but `reasoning_content` is NOT exposed in streaming deltas — the frontend won't show a thinking bubble. Usage reports `reasoning_tokens` at top level (not inside `completion_tokens_details`).
- **`/responses`** (gpt-5.4-mini, gpt-5.4, etc.): Reasoning summary is streamed via `response.reasoning_summary_text.delta` events and exposed as `reasoning_content` — the frontend shows a thinking bubble. `output_tokens_details.reasoning_tokens` reports usage.

### Reasoning token scaling

**gpt-5.4-mini** (`/responses` — visible thinking):

| Level    | Reasoning tokens | Summary chars |
| -------- | ---------------- | ------------- |
| `low`    | ~12              | ~400          |
| `medium` | ~130             | ~500          |
| `high`   | ~200             | ~400          |

**gpt-5-mini** (`/chat/completions` — hidden thinking):

| Level    | Reasoning tokens | Visible content | Latency |
| -------- | ---------------- | --------------- | ------- |
| none     | 0                | ~370 chars      | ~7s     |
| `low`    | ~4               | ~370 chars      | ~7s     |
| `medium` | ~600             | ~340 chars      | ~15s    |
| `high`   | ~1024            | ~80 chars       | ~18s    |

Note: gpt-5-mini is free (0x multiplier) so higher reasoning costs nothing extra but adds significant latency.

### Copilot API quirks

- **`reasoning_tokens` location**: Copilot returns `reasoning_tokens` at the **top level** of the usage object, not inside `completion_tokens_details`. Our `_usage_from_openai()` helper checks both locations.
- **`stream_options`**: `stream_options: {include_usage: true}` is supported on Copilot's completions endpoint (previously we omitted it — now enabled for accurate usage reporting).

### Cost impact

Reasoning tokens count as output tokens for billing. Higher `thinking_level` = more output tokens = same premium request cost (Copilot bills per request, not per token), but longer latency.

## Notes

- Counters reset on the **1st of each month** at 00:00 UTC
- Unused requests **do not** roll over
- When premium requests run out, you can still use included models (GPT-5 mini, GPT-4.1, GPT-4o)
- Rate limits may apply during high demand periods
