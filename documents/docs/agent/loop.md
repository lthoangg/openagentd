---
title: Agent Loop & Execution
description: One-turn reasoning loop with iteration, tool dispatch, checkpointing, and interrupts.
status: stable
updated: 2026-04-21
---

# Agent Loop

**Source:** `app/agent/agent_loop.py`

The `Agent` class drives all LLM reasoning in openagentd. One `Agent.run()` call = one user turn.

---

## Construction

```python
from app.agent.agent_loop import Agent
from app.agent.providers.googlegenai import GoogleGenAIProvider

provider = GoogleGenAIProvider(api_key="...", model="gemini-2.0-flash", temperature=0.7)

agent = Agent(
    llm_provider=provider,
    name="assistant",
    system_prompt="You are a helpful assistant.",
    tools=[web_search, date],
    hooks=[StreamingHook()],
    max_iterations=100,
    max_concurrent_tools=10,
)
```

| Parameter | Default | Notes |
|-----------|---------|-------|
| `llm_provider` | required | Any `LLMProviderBase` implementation |
| `name` | `"Agent"` | Appears in SSE `agent` field and logs |
| `system_prompt` | `"You are a helpful assistant."` | Stored in `state.system_prompt`; prepended as `SystemMessage` inside `_stream_and_assemble` per LLM call |
| `tools` | `[]` | `Tool` objects or plain callables decorated with `@tool` |
| `hooks` | `[]` | `BaseAgentHook` instances — run in order |
| `max_iterations` | `100` | Guards against infinite tool-call loops |
| `max_concurrent_tools` | `10` | Semaphore for parallel tool execution |
| `context` | `None` | Optional `AgentContext` subclass; accessible as `state.context` in hooks |
| `fallback_provider` | `None` | Secondary `LLMProviderBase` used when primary exhausts retries on retryable errors |
| `fallback_model_id` | `None` | `"provider:model"` string for logging (e.g. `"copilot:gpt-5-mini"`) |
| `summarization_config` | `None` | `SummarizationConfig` from YAML; read by `build_summarization_hook` in the route/team member to wire `SummarizationHook` per turn |

---

## Running a turn

```python
from app.agent.schemas.agent import RunConfig

config = RunConfig(session_id=str(session_id))
messages = await get_messages_for_llm(db, session_id)
checkpointer = SQLiteCheckpointer(session_factory)
result_messages = await agent.run(messages, config=config, checkpointer=checkpointer)
```

`agent.run()` signature:

```python
async def run(
    messages: list[ChatMessage],
    config: RunConfig | None = None,
    *,
    hooks: Sequence[AgentHook] | None = None,
    injected_tools: list[Tool] | None = None,
    interrupt_event: asyncio.Event | None = None,
    checkpointer: Checkpointer | None = None,
    **kwargs,
) -> list[ChatMessage]:
```

- `hooks` and `injected_tools` are **merged** with constructor values — never replace them.
- `messages` is copied; the caller's list is never mutated.
- Returns the full message list including new assistant + tool messages appended this turn.
- Pass `checkpointer=None` (default) to skip all persistence — useful for unit tests.

See `app/agent/agent_loop.py:Agent.__init__` and `Agent.run()` for full signature details.

---

## Loop internals

```
agent.run(messages, checkpointer=checkpointer)
│
├─ Create RunContext(session_id, run_id, agent_name, session_created_at)   ← frozen, immutable
├─ Strip any SystemMessage from input messages         ← system prompt never lives in state.messages
├─ Build AgentState(messages, capabilities, tool_names, ...)  ← mutable, per-run
├─ Build tool hook chain (build_tool_chain)
│
├─ Fire before_agent(ctx, state) on all hooks
│
└─ while iteration < max_iterations:
    ├─ Build ModelRequest(messages=state.messages_for_llm, system_prompt=state.system_prompt)
    │
    ├─ Fire before_model(ctx, state, request) on all hooks
    │    ├─ TeamInboxHook (team only): drains mailbox queue, persists + SSE-emits new inbox
    │    │  messages, appends them to state.messages, returns updated ModelRequest
    │    └─ Hook may return modified ModelRequest (e.g. SummarizationHook, TeamInboxHook)
    │       ModelRequest.messages is a frozen tuple snapshot — hooks that mutate
    │       state.messages MUST return request.override(messages=...) or the LLM sees stale data
    │
    ├─ checkpointer.sync(ctx, state)                   ← sync point 1: after before_model
    │
    ├─ build_model_chain → invoke wrap_model_call chain with model_request
    │    └─ Innermost: _stream_and_assemble(req, ctx, state, hooks, interrupt_event, tool_defs)
    │         ├─ Prepends SystemMessage(req.system_prompt) at index 0 for provider call
    │         ├─ _stream_with_retry(messages=[SystemMessage, ...req.messages], tools=tool_defs|None)
    │         │    └─ llm_provider.stream(...)  — yields ChatCompletionChunk
                │         ├─ Fire on_model_delta(ctx, state, chunk) per chunk
                │         │    ├─ StreamingHook queues chunk to asyncio.Queue
                │         │    └─ StreamPublisherHook pushes thinking/message/tool_call to stream store
    │         ├─ Buffers: full_content, reasoning, tool_calls_buffer (indexed by tc.index)
    │         └─ Returns AssistantMessage; stores usage in self._last_usage
    │
    ├─ Read self._last_usage; populate state.usage (last_prompt_tokens, total_tokens, …)
    ├─ Fire after_model(ctx, state, assistant_msg)
    │    └─ SessionLogHook writes JSONL event
    │
    ├─ checkpointer.sync(ctx, state)                   ← sync point 2: after after_model
    │
    ├─ If no tool_calls → BREAK (final answer)
    │
    ├─ ★ Pre-dispatch interrupt check
    │    └─ If interrupt_event.is_set(): append ToolMessage("Cancelled by user.") per tool call → BREAK
    │
    ├─ _gather_or_cancel([_run_tool(ctx, state, tc) for tc in tc_list], interrupt_event)
    │    ├─ Each tool: semaphore-bounded → tool hook chain → execute_fn
                │    │    ├─ StreamingHook.wrap_tool_call: queue ToolStartSignal, execute, queue ToolEndSignal
                │    │    └─ StreamPublisherHook.wrap_tool_call: push tool_start, execute, push tool_end
    │    └─ On interrupt mid-execution:
    │         ├─ Completed tools keep their real results
    │         ├─ Still-running tools are cancelled → ToolMessage("Cancelled by user.")
    │         └─ Loop breaks after appending all ToolMessages
    │
    ├─ Append ToolMessage per result (if tool returned ToolResult → attach .parts)
    ├─ checkpointer.sync(ctx, state)                   ← sync point 3: after tool execution
    └─ loop
│
├─ Fire after_agent(ctx, state, last_assistant_msg)
│    └─ StreamingHook puts _SENTINEL → SSE consumer raises StopAsyncIteration
│
└─ checkpointer.sync(ctx, state)                       ← sync point 4: after after_agent
```

---

## Tool call buffering

The loop buffers streaming tool-call deltas by `tc.index` — providers stream arguments incrementally, with `.id` set on first appearance and never overwritten (see `app/agent/agent_loop/core.py:155-170`).

**Critical:** `id` is set on first appearance and never overwritten. Some providers resend IDs on continuation chunks — overwriting causes `tool_end` to carry the wrong ID downstream.

**Provider contract — `.index` must be stable per `id`.** The buffer is keyed by `idx`, so a provider that changes the index of an already-seen id between chunks will trigger the `tool_call_index_collision` warning (`app/agent/agent_loop/streaming.py:121`) and leak a duplicate pending tool card onto the UI (`StreamPublisherHook.on_model_delta` emits a second `tool_call` SSE event for the new id, and that card never receives `tool_start`/`tool_end`). Gemini SSE chunks carry a complete snapshot of the candidate's `parts` array every chunk, so naive `enumerate(parts)` indexing breaks this contract when a `thought` part shifts positions mid-stream. Both Gemini providers (`googlegenai.py`, `geminicli.py`) now assign a stream-scoped `tool_idx_by_id.setdefault(fc_id, len(tool_idx_by_id))` before building each `ToolCallDelta`, guaranteeing the same id keeps the same slot across chunks.

---

## Retry logic and fallback model

`_stream_with_retry()` wraps the provider call with exponential-backoff retry and optional fallback:

| Status | Behaviour |
|--------|-----------|
| `429 Too Many Requests` | Retry; parse `Retry-After` from header or body |
| `500 / 502 / 503 / 504` | Retry with exponential backoff |
| `400 Bad Request` | Raise immediately — malformed request won't self-heal |
| `ConnectError / ReadTimeout` | Retry |

Retry schedule: `min(1 × 3^attempt, 60)` seconds (1s, 3s, 9s, 27s, 60s). On the **last** attempt, no sleep — immediately move to fallback (or raise).

On `429`, fires `on_rate_limit(ctx, state, retry_after, attempt, max_attempts)` on all hooks before sleeping, so `StreamingHook` can push a `rate_limit` SSE event to the client.

### Fallback model

If `fallback_provider` is set on the Agent, the retry loop iterates over two providers:

```
Primary provider (5 retries)
  → all retries exhausted?
    → llm_provider_exhausted logged
    → llm_provider_fallback logged
    → Fallback provider (5 retries)
      → success? return
      → all retries exhausted? raise last exception
```

- Non-retryable errors (400, 401, 403) are raised immediately — no fallback.
- The fallback provider gets the same retry budget (5 attempts with backoff).
- Configured via `fallback_model` in the agent's `.md` frontmatter (see [configuration.md](../configuration.md#fallback-model)).

### Key log events (retry/fallback)

| Log event | Level | Meaning |
|-----------|-------|---------|
| `llm_provider_retry` | WARNING | Retrying after a transient error (includes model, status, attempt, delay) |
| `llm_provider_exhausted` | WARNING | All retry attempts exhausted for a provider |
| `llm_provider_fallback` | WARNING | Switching from primary to fallback provider |
| `llm_provider_error` | ERROR | Non-retryable error — raised immediately |

---

## Interrupt

Pass an `asyncio.Event` as `interrupt_event`. The loop checks it at three points:

1. **During LLM streaming** — after each chunk, breaks out of the stream.
2. **Before tool dispatch** — if already set when tools are about to execute, skips execution entirely and returns `"Cancelled by user."` for every tool call.
3. **During tool execution** — `_gather_or_cancel()` monitors the event while tools run in parallel. Completed tools keep their real results; still-running tools are cancelled via `asyncio.Task.cancel()` and get `"Cancelled by user."` as their result.

```python
interrupt = asyncio.Event()
task = asyncio.create_task(agent.run(messages, interrupt_event=interrupt))
interrupt.set()   # cancel mid-stream or mid-tool-execution
```

Team members use this for user-initiated interrupts. After the run, the last assistant message is annotated with `" [interrupted]"` in the DB.

### `_gather_or_cancel` — cancellable parallel tool execution

`_gather_or_cancel(coros, interrupt_event, tc_list)` replaces the previous `asyncio.gather()` call. It uses `asyncio.wait(FIRST_COMPLETED)` in a loop, racing tool tasks against the interrupt event:

```
Tool A (fast)  ──── done ✓  real result kept
Tool B (medium) ─────── done ✓  finished same tick as cancel — real result kept
Tool C (slow)   ──────────── CANCEL ✗  "Cancelled by user."
                                  ↑
                           interrupt_event.set()
```

When `interrupt_event` is `None`, falls back to plain `asyncio.gather(..., return_exceptions=True)` — zero overhead for non-interruptible runs.

### HTTP-layer interrupt (team mode)

`POST /api/team/chat` with `interrupt=true` triggers the interrupt via team interrupt handling:

```
POST /api/team/chat  interrupt=true  session_id=<sid>
│
├─ AgentTeam interrupts current member run
│    └─ interrupt_event.set()     ← loop breaks after current chunk or cancels tools
└─ return {"status": "interrupted", "session_id": "..."}
```

The checkpointer (`SQLiteCheckpointer`) has already saved partial output at the most recent `sync()` call — no assistant text is lost. Empty assistant messages (interrupted before any content, reasoning, or tool calls were generated) are skipped during `sync()` to avoid persisting no-op rows. Once the loop exits, the SSE stream emits a final `done` event with `cancelled: true` in metadata, signalling clients to reload from DB.

### Non-graceful interrupt — orphaned tool calls

Sync point 2 (after `after_model`) persists the `AssistantMessage` with `tool_calls` *before* dispatch starts; sync point 3 persists the matching `ToolMessage` rows. A crash, SIGKILL, or `--dev` reload between those two points leaves the assistant turn on disk with no tool replies. The next user turn would then 400 against any provider that enforces the assistant→tool pairing (OpenAI Responses: `"No tool output found for function call …"`).

`AgentTeam.handle_user_message` calls `chat_service.heal_orphaned_tool_calls()` immediately before persisting the new user message. The helper inspects the latest assistant row and inserts a synthetic `ToolMessage("Tool execution was interrupted before a result could be recorded.")` for any `tool_call_id` without a matching reply. Stub timestamps anchor to `last_assistant.created_at + 1µs * (i+1)` so the LLM input order stays `assistant{tool_calls} → tool → … → user` even when wall-clock writes collide. Heal runs in the same transaction as the user-message insert (atomic) and is a no-op when the latest turn is healthy. See `app/services/chat_service.py:heal_orphaned_tool_calls` for the implementation and `tests/services/test_chat_service.py` (`test_heal_*`) for the contract.

---

## Concurrency safety

- `self._tools` is never mutated after construction — `agent.run()` builds a local `run_tools` copy.
- The `_tool_semaphore` (default 10) bounds parallel tool calls.
- `self.state` (`AgentStats`) — cumulative stats object, safe to read between turns.
- `AgentState` — per-run, created fresh each call, not shared between concurrent runs.
- `RunContext` — frozen dataclass, safe to share across concurrent hooks and tool calls.

---

## Key log events

| Log event | Level | Key fields |
|-----------|-------|-----------|
| `agent_run_start` | INFO | `agent`, `message_count`, `tools`, `session` |
| `agent_iteration` | INFO | `agent`, `iteration`, `max_iterations`, `messages` |
| `llm_response` | INFO | `agent`, `iteration`, `elapsed`, `content_len`, `reasoning_len`, `tool_calls`, token counts |
| `llm_usage_detail` | DEBUG | `cached_tokens`, `thoughts_tokens`, `tool_use_tokens` |
| `tool_dispatch` | INFO | `agent`, `count`, tool names |
| `tool_dispatch_skipped_interrupt` | INFO | `agent`, `count` — interrupt was set before tool execution started |
| `tool_start` | INFO | `agent`, `tool`, `id`, args preview |
| `tool_done` | INFO | `agent`, `tool`, `elapsed`, `result_len` |
| `tool_cancelled` | INFO | `agent`, `tool` — tool was cancelled mid-execution by interrupt |
| `tool_call_orphans_healed` | WARNING | `session_id`, `count`, `ids` — synthetic tool replies inserted before next turn (server crash recovery) |
| `tool_error` | ERROR | `agent`, `tool`, `elapsed`, `error` |
| `agent_run_done` | INFO | `agent`, `elapsed`, `iterations`, `total_messages`, `total_tokens` (from `state.usage.total_tokens`) |
