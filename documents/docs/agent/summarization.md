---
title: Rolling-Window Context Summarization
description: Automatic conversation compression when context window approaches token threshold.
status: stable
updated: 2026-04-21
---

# Summarization

**Source:** `app/agent/hooks/summarization.py`

`SummarizationHook` implements rolling-window context compression: when the LLM's prompt token count crosses a threshold, older messages are replaced with a compact summary, keeping the context window manageable without losing history.

---

## Design principles

| Property | Detail |
|----------|--------|
| **Pure state transform** | Reads `state.usage.last_prompt_tokens` and mutates `state.messages` directly. No DB access inside the hook. |
| **In-memory trigger** | Token count comes from `state.usage.last_prompt_tokens`, populated by the loop after each LLM call. |
| **Non-destructive** | Old messages are marked `exclude_from_context=True` in-memory; the Checkpointer persists this to DB. Full history remains. |
| **UI transparent** | Summary rows (`is_summary=True`) are never returned to the UI. Users see the full unabridged conversation. |
| **Minimum-delta guard** | `_messages_at_last_summary` tracks the message count at the last summarisation. If fewer than `min_messages_since_last_summary` new messages have arrived, the hook skips — prevents thrashing when the kept window sits close to the threshold. |
| **Tool result stubbing** | `ToolMessage` content is replaced with `[tool/name]: [tool result omitted]` in the summariser input. Raw shell output, file contents, and JSON blobs are noise for summarisation; the tool name is sufficient. |
| **Merge vs. fresh summary** | When the window being summarised contains a prior summary (`is_summary=True`), the hook sends a merge instruction (`_MERGE_REQUEST`) instead of the default request. The summariser is told explicitly to fold old and new content together. |
| **LLM exception** | Calls an LLM to generate the summary text — the only I/O this hook performs. |

---

## Configuration

Settings are resolved from three tiers in priority order (first non-`None` wins):

1. **Per-agent frontmatter** — `summarization:` block in the agent's `.md` file
2. **Global file config** — `.openagentd/config/summarization.md` (YAML frontmatter)
3. **Module-level defaults** — `DEFAULT_*` constants in `app/agent/hooks/summarization.py`

### Global file config (`.openagentd/config/summarization.md`)

The primary way to set the summarizer prompt, shared summarizer model, and default thresholds for all agents. Create or edit `.openagentd/config/summarization.md`:

```markdown
---
model: googlegenai:gemini-2.0-flash   # default summarizer model for all agents
token_threshold: 100000
keep_last_assistants: 3
max_token_length: 10000
---

You are a conversation summariser. Produce a concise but complete summary of
the conversation so far. Capture key facts, decisions, and outcomes.
```

All frontmatter fields are optional — any field omitted falls back to the module-level defaults.

**The Markdown body is the summariser system prompt, and it is required.** If the file is missing while summarization is enabled (`token_threshold > 0`), `build_summarization_hook` logs a warning and returns `None` (the hook is skipped — sessions run without summarization). An empty body does the same. There is no bundled fallback prompt — the config file is the single source of truth. Set per-agent `summarization.enabled: false` (or `token_threshold: 0` in the file config) to disable summarization entirely.

The path is `{OPENAGENTD_CONFIG_DIR}/summarization.md`, computed by `summarization_config_path()` in `app/agent/hooks/summarization.py`.

`SummarizationFileConfig` (defined in `app/agent/schemas/agent.py`) is the Pydantic model for this file. `load_summarization_file_config()` in `app/agent/loader.py` parses the frontmatter, captures the body as `prompt`, and caches the result; pass an explicit `path` argument to bypass the cache (useful in tests).

### Module-level defaults

Final fallback when neither per-agent config nor the global file config specifies a field. The `DEFAULT_*` constants live at the top of `app/agent/hooks/summarization.py`. To tune for local testing (e.g. `token_threshold: 2000`) prefer setting it in `.openagentd/config/summarization.md` rather than editing the source.

### Per-agent overrides (YAML frontmatter)

Each agent can override any tier-2 or tier-3 value with a `summarization:` block in its `.md` frontmatter. All fields are optional; any field omitted falls through to the file config, then to the module-level defaults.

```yaml
summarization:
  enabled: true                         # false = disable summarization for this agent only
  token_threshold: 60000                # overrides file config / DEFAULT_PROMPT_TOKEN_THRESHOLD
  keep_last_assistants: 2               # overrides file config / DEFAULT_KEEP_LAST_ASSISTANTS
  max_token_length: 5000                # overrides file config / DEFAULT_MAX_TOKEN_LENGTH
  model: googlegenai:gemini-flash-lite  # overrides file config model (agent-specific summarizer)
```

Team agents have independent configs — one member can have summarization disabled while another uses a lower threshold.

The per-agent config is stored on `agent.summarization_config` (a `SummarizationConfig` instance or `None`) and is read by `build_summarization_hook` in `chat.py` and `team/member.py` when constructing the hook for each turn.

`SummarizationConfig` is defined in `app/agent/schemas/agent.py` and re-exported from `app/agent/loader.py`.

### In code

Use `build_summarization_hook` to construct a hook from a `SummarizationConfig` with settings fallback:

```python
from app.agent.hooks.summarization import build_summarization_hook

hook = build_summarization_hook(default_provider=provider, cfg=agent.summarization_config)
if hook:
    hooks.append(hook)
```

Returns `None` when summarization is disabled (`cfg.enabled=False` or `threshold <= 0`), so the caller only needs an `if` check.

To construct `SummarizationHook` directly (e.g. for custom integrations):

```python
from app.agent.hooks.summarization import SummarizationHook

hook = SummarizationHook(
    llm_provider=provider,                    # can be a cheaper/faster model
    prompt_token_threshold=100000,
    keep_last_assistants=3,                   # keep last 3 assistant turns + their preceding context
    summary_prompt="...",                     # system prompt for summariser
    max_token_length=10000,                   # limit response to 10k tokens (0 = unlimited)
    min_messages_since_last_summary=4,        # skip if fewer than 4 new messages since last run
)
```

No `session_factory` — the hook does not open DB sessions.

### max_token_length parameter

The `max_token_length` parameter limits the number of tokens in the summarization LLM's response. This is passed to the provider's API as:

| Provider | API Parameter |
|----------|---------------|
| OpenAI | `max_output_tokens` |
| Google Gemini / VertexAI / GeminiCLI | `max_output_tokens` |
| ZAI | `max_tokens` |
| Copilot | `max_output_tokens` |

**Benefits:**
- **Cost control** — Limits summarization response size and API costs
- **Latency reduction** — Prevents runaway summarization calls
- **Provider-agnostic** — Works with all supported LLM providers
- **Server-side enforcement** — No truncation in our code; the API handles the limit

Set to `0` to disable (no limit). Default is `10000` tokens.

---

## Trigger flow

```
before_model(ctx, state)
│
├─ threshold <= 0? → skip
│
├─ state.usage.last_prompt_tokens < threshold? → skip
│
├─ acquire _lock
├─ _summarising already? → skip (re-entrant guard)
├─ set _summarising = True
│
     └─ _summarise(state)
     ├─ messages = [m for m in state.messages if not m.exclude_from_context and not isinstance(m, SystemMessage)]
     ├─ find cutoff: walk backward, count assistant messages
     │    cutoff = index of Nth-from-last assistant message (keep_last_assistants)
     │    to_summarise = messages[:cutoff]
     │    to_keep      = messages[cutoff:]      (last N assistant turns + context)
     │    if fewer than N assistant turns exist → to_summarise = all messages
     │
     ├─ Build summariser prompt:
     │    [SystemMessage(summary_prompt)]
     │    + [HumanMessage("Please summarise...\n\n[role]: content\n...")]
     │
     ├─ _call_llm(summariser_messages) → summary_text
     │
     ├─ Mark to_summarise messages: exclude_from_context=True (in-place mutation)
     │
     ├─ Exclude any prior is_summary=True messages still in kept window (superseded)
     │
     ├─ Create HumanMessage("[Summary of earlier conversation]\n" + summary_text, is_summary=True)
     │
     └─ Insert summary at first non-excluded position in state.messages
          → state.messages is now updated in-memory
          → loop calls checkpointer.sync() after before_model, persisting changes to DB
```

---

## Message lifecycle

```
Turn 1–20:  All messages in state.messages, accumulating prompt tokens
Turn 21:    state.usage.last_prompt_tokens ≥ threshold
            → before_model fires summarization
            → Cutoff = index of 3rd-from-last assistant message (keep_last_assistants=3)
            → Older messages: exclude_from_context=True (mutated in state.messages)
            → Last 3 assistant turns + preceding context: remain included
            → New summary HumanMessage inserted: is_summary=True
            → checkpointer.sync() persists all changes to DB

LLM context from Turn 21 onward (via state.messages_for_llm):
  [system]
  [user: [Summary of earlier conversation]\n...]
  [last 3 assistant turns + context verbatim]
  [new user message]
```

---

## messages_for_llm behaviour

`state.messages_for_llm` is a computed property that filters `state.messages`:

The loop sends `state.messages_for_llm` to the LLM (see `app/agent/state.py:AgentState.messages_for_llm`) — never raw `state.messages`. Multiple summarization rounds work correctly: only the latest summary is included; older summaries are excluded by `exclude_from_context=True` set during the next summarization cycle.

---

## DB schema

| Column | Value after summarization |
|--------|--------------------------|
| `exclude_from_context` | `True` for summarised messages (persisted by `checkpointer.sync()`) |
| `is_summary` | `True` for the summary message |
| `role` | `user` for summary (`HumanMessage` — keeps `system → user → ...` invariant valid for all providers including ZAI) |
| `extra.usage` | Token counts written by `checkpointer.sync()` — read back as `state.usage.last_prompt_tokens` on next turn |

---

## Using a different model for summarization

The recommended approach is to set `model` in `.openagentd/config/summarization.md` — this applies the same cheap/fast summarizer model to all agents at once:

```markdown
---
model: googlegenai:gemini-2.0-flash   # all agents use this for summarization
---
```

To override for a specific agent, add `model` to the agent's `summarization:` block:

```yaml
summarization:
  model: googlegenai:gemini-flash-lite   # only this agent uses a different summarizer
```

Priority: per-agent `model` → file config `model` → agent's own provider (no separate summarizer).

A separate provider instance is created at startup from the resolved model string and passed to `SummarizationHook`. The agent's main `llm_provider` is unaffected.

In code, `build_summarization_hook` handles the model resolution automatically. For manual construction, pass any `LLMProviderBase` as `llm_provider`:

```python
summarizer_provider = ZAIProvider(api_key="...", model="glm-4-flash")
main_provider = GoogleGenAIProvider(api_key="...", model="gemini-2.0-flash")

hook = SummarizationHook(
    llm_provider=summarizer_provider,   # cheap summarizer
    prompt_token_threshold=100000,
)
agent = Agent(llm_provider=main_provider, hooks=[hook])
```

---

## Disabling summarization

**Globally:** set `token_threshold: 0` in `.openagentd/config/summarization.md`. The hook becomes a no-op immediately in `before_model`.

**Per agent:** set `enabled: false` in the agent's `summarization:` block (YAML):

```yaml
summarization:
  enabled: false
```

When `enabled: false`, the hook is not added to that agent's hook list at all for the turn.

---

## Observability

`SummarizationHook` emits OTel spans directly (it bypasses `OpenTelemetryHook` because it calls the LLM outside the agent hook lifecycle).

### Span hierarchy

```
summarization                   ← _summarise(); parent = active agent_run span if present
  └── summarization_llm_call    ← _call_llm(); the streaming LLM request
```

### `summarization` span attributes

| Attribute | Value |
|-----------|-------|
| `gen_ai.agent.name` | agent name |
| `gen_ai.conversation.id` | session_id |
| `run_id` | unique per turn |
| `summarization.prompt_tokens` | `state.usage.last_prompt_tokens` at trigger time |
| `summarization.threshold` | configured token threshold |
| `summarization.messages_to_summarise` | messages being compressed |
| `summarization.keep_last_assistants` | configured keep window |
| `summarization.summary_length` | char length of generated summary |
| `summarization.kept` | messages kept verbatim |
| `summarization.skipped` | reason if no LLM call was made (`"no_messages"`, `"all_in_keep_window"`, `"empty_llm_response"`) |
| `error.type` | exception class name (only on error) |

### `summarization_llm_call` span attributes

| Attribute | Value |
|-----------|-------|
| `summarization.llm_duration_s` | elapsed seconds for the streaming call |
| `summarization.response_length` | char length of the raw LLM response |
| `error.type` | exception class name (only on error) |

Inspect with:

```bash
uv run python -m manual.otel_inspect --summary          # [summarize] rows in duration table
uv run python -m manual.otel_inspect --op summarization # raw span list
```

---

## Failure modes

| Failure | Behaviour |
|---------|-----------|
| LLM summarization call fails | Logs error, returns without mutating state. Next turn re-evaluates. |
| Empty summary response | Logs warning, skips. Messages remain included. |
| No eligible messages in state | Logs debug, skips. |
| `last_prompt_tokens` is 0 | Hook is silently a no-op (no LLM call yet this turn). Happens on the first turn of a fresh session — tokens are seeded from history on resume (see below). |
| SystemMessage in summary | **Fixed.** `eligible` now excludes `isinstance(m, SystemMessage)` — the agent's system prompt is never passed to the summariser LLM. Team members are also protected since the system prompt is injected by the agent loop into `state.messages` (not DB), and the fix applies uniformly. |
| Too few new messages since last summary | `_messages_at_last_summary` guard logs debug and skips. Prevents thrashing when the kept window already sits close to the threshold. |

---

## Cross-request token seeding (session resume)

`state.usage.last_prompt_tokens` starts at `0` on every new `Agent.run()` call. Without seeding, the hook would never fire on turn 2+ of a multi-HTTP-request session because `before_model` always sees `0`.

**Fix:** Seeding is centralised in `SQLiteCheckpointer` — no call-site workarounds needed.

```
mark_loaded(session_id, history)
  → _last_prompt_tokens_from_history(history)
       scans history in reverse for last assistant extra.usage.input
       stores result in _seeded_tokens[session_id]

agent_loop.py — after building AgentState:
  if checkpointer has seed_state:
      checkpointer.seed_state(session_id, state)
          → state.usage.last_prompt_tokens = _seeded_tokens[session_id]
```

Both the single-agent path (`POST /api/chat`) and the team member path (`member.py._handle_messages`) call `mark_loaded()` then pass the checkpointer to `agent.run()`. The loop calls `seed_state()` automatically — both paths get correct seeding with no extra code per call site.

`_last_prompt_tokens_from_history` is a module-level helper in `checkpointer.py` that extracts the last prompt token count from the message history (see `app/services/checkpointer.py`).

---

## HumanMessage exclusion (checkpointer fix)

Prior to this fix, `SummarizationHook` marked all summarised messages (`to_summarise`) as `exclude_from_context=True` in-memory, but the `SQLiteCheckpointer._update_exclude_flags()` method only persisted this flag for `AssistantMessage` and `ToolMessage`. `HumanMessage` exclusions were silently dropped, leaving orphaned user messages visible to the LLM without their paired assistant replies.

**Fix:** `_update_exclude_flags` now processes all message types except `SystemMessage`. `HumanMessage` objects are also registered into `persisted_ids` during `sync()` (without a DB insert — the route handler already saved them) so the flag-flip tracking works correctly on subsequent turns.

`db_id` is now populated on all message types during `_deserialize_messages()`, enabling reliable PK-based DB lookups instead of fragile content-match fallback.

---

## Interaction with teams

`SummarizationHook` is attached to each `TeamMemberBase` (lead or member) independently in `_handle_messages()`. Each agent has its own `AgentState` and its own `state.usage.last_prompt_tokens` accumulation. Summarization fires per-agent when that agent's prompt tokens exceed the threshold — not globally across the team. Each agent's `SQLiteCheckpointer` persists the resulting state mutations independently.

Each team agent can carry its own `summarization:` block in its `.md` frontmatter. Any field not set in the agent's block falls back to the global `.openagentd/config/summarization.md` file, then to module-level defaults:

```markdown
---
name: orchestrator
role: lead
model: zai:glm-5v-turbo
summarization:
  token_threshold: 80000
---
```

```markdown
---
name: explorer
role: member
model: zai:glm-5-turbo
summarization:
  enabled: false     # explorer has short turns — skip summarization
---
```

Agents with no `summarization:` block fall back to the global file config, then to module-level defaults.

Token seeding on team member resume works identically to single-agent: `mark_loaded()` + `seed_state()` are called inside `_handle_messages()` before every `agent.run()`, so each member wakes up with the correct prior token count regardless of which HTTP request triggered the turn.
