---
title: Manual Team Testing Guide
description: Step-by-step procedures for validating multi-agent delegation, task board, interrupts, and error recovery.
status: stable
updated: 2026-04-29
---

# Manual Test Guide — Agent Teams

**Prereq:** `team:` section present in `app/agents/agents.yaml` with lead + members configured.

## Setup

**Terminal A — server:**
```sh
uv run uvicorn app.server:app
```

**Terminal B — curl / httpie:**
```sh
# SSE stream (keep open in background)
curl -N http://localhost:8000/team/stream

# Send messages
curl -X POST http://localhost:8000/team/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you do?"}'
```

---

## Startup checks (Terminal A)

```
INFO | agent_config_loaded name=orchestrator ...
INFO | agent_config_loaded name=explorer ...
INFO | agent_config_loaded name=executor ...
INFO | agent_config_loaded name=consultant ...
INFO | team_loaded name=task-force lead=orchestrator members=['explorer', 'executor', 'consultant']
INFO | team_member_started name=orchestrator session_id=...
INFO | team_member_started name=explorer session_id=...
INFO | team_member_started name=executor session_id=...
INFO | team_member_started name=consultant session_id=...
INFO | agent_team_started name=task-force lead=orchestrator members=['explorer', 'executor', 'consultant']
INFO | team_started name=task-force
```

**Pass:** All four agents loaded, registered in mailbox, no errors.
**Fail:** Missing agent, import error, or DB session creation failure.

---

## Test 1 — Team status (sanity check)

```sh
curl http://localhost:8000/team/status
```

**Expected:**
```json
{
  "team": "task-force",
  "lead": {"name": "orchestrator", "state": "available"},
  "members": [
    {"name": "explorer", "state": "available"},
    {"name": "executor", "state": "available"},
    {"name": "consultant", "state": "available"}
  ]
}
```

**Pass:** All agents available, correct names.

---

## Test 2 — Basic delegation (happy path)

**SSE stream open in one terminal, then send:**
```sh
curl -X POST http://localhost:8000/team/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Research the latest advances in quantum computing in 2025 and analyse the key trends."}'
```

**Expected response:**
```json
{"status": "accepted", "session_id": "..."}
```

**Expected SSE event sequence (approximate):**
```
event: agent_status     data: {"agent": "orchestrator", "status": "working"}
event: tool_start       data: {"agent": "orchestrator", "name": "create_tasks", ...}
event: tool_end         data: {"agent": "orchestrator", "name": "create_tasks"}
event: tool_start       data: {"agent": "orchestrator", "name": "send_message", ...}
event: tool_end         data: {"agent": "orchestrator", "name": "send_message"}
event: message          data: {"agent": "orchestrator", "text": "Delegating..."}
event: agent_status     data: {"agent": "orchestrator", "status": "available"}

event: agent_status     data: {"agent": "explorer", "status": "working"}
event: tool_start       data: {"agent": "explorer", "name": "claim_task", ...}
event: tool_start       data: {"agent": "explorer", "name": "web_search", ...}
event: message          data: {"agent": "explorer", "text": "..."}
event: agent_status     data: {"agent": "explorer", "status": "available"}

event: agent_status     data: {"agent": "executor", "status": "working"}
event: tool_start       data: {"agent": "executor", "name": "claim_task", ...}
event: message          data: {"agent": "executor", "text": "..."}
event: agent_status     data: {"agent": "executor", "status": "available"}

event: agent_status     data: {"agent": "orchestrator", "status": "working"}     # lead wakes on member replies
event: message          data: {"agent": "orchestrator", "text": "Here is the summary..."}
event: agent_status     data: {"agent": "orchestrator", "status": "available"}
event: done             data: {}
```

**Expected logs:**
```
INFO | team_chat_received session_id=... interrupt=False lead=orchestrator
INFO | team_member_activated name=orchestrator messages=1
INFO | tool_start agent=orchestrator tool=create_tasks
INFO | tool_start agent=orchestrator tool=send_message
INFO | team_member_available name=orchestrator
INFO | team_member_activated name=explorer messages=1
INFO | team_member_early_exit agent=explorer ...    # message_leader(stop=true)
INFO | team_member_available name=explorer
INFO | team_member_activated name=executor messages=1
INFO | team_member_early_exit agent=executor ...
INFO | team_member_available name=executor
INFO | team_member_activated name=orchestrator messages=2     # drains both replies
INFO | team_member_available name=orchestrator
INFO | team_turn_done name=task-force
```

**Key checks:**
- [ ] 202 returned immediately (not blocking)
- [ ] Lead creates tasks on the board before delegating
- [ ] Both members wake and work in parallel
- [ ] Members call `message_leader(stop=true)` — look for `team_member_early_exit`
- [ ] Lead wakes a second time, drains member replies, produces final synthesis
- [ ] `done` event fires exactly once, after all agents become available
- [ ] No spurious `done` events before members finish

**Pass:** Full round-trip completes. Lead synthesises member outputs into final answer.
**Fail:** Agent hangs, `done` never fires, members don't wake, or lead doesn't synthesise.

---

## Test 3 — Task board state

After Test 2 completes, verify the board:

```sh
curl http://localhost:8000/team/status
```

All agents should be `available`. There is no board API yet, but check server logs for:
```
INFO | tool_done ... tool=create_tasks result="Created 2 task(s): task_1, task_2"
INFO | tool_done ... tool=claim_task result="Claimed task task_1."
INFO | tool_done ... tool=update_task_status result="Task task_1 status: in_progress → completed."
```

**Pass:** Tasks created, claimed, completed in order.
**Fail:** Tasks stuck `in_progress`, or claim fails.

---

## Test 4 — Session continuity (lead session)

Send a follow-up using the same `session_id` from Test 2:

```sh
curl -X POST http://localhost:8000/team/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Can you go deeper on the second trend you mentioned?", "session_id": "<session_id_from_test_2>"}'
```

**Expected:**
- Lead wakes and sees the follow-up in context of the previous conversation
- Lead may re-delegate or answer directly depending on LLM judgement
- Members retain their own history from the first task

**Pass:** Lead references previous findings. Response is contextual, not confused.
**Fail:** Lead acts like it's a fresh conversation, or errors on session lookup.

---

## Test 5 — Fresh session (new session_id)

```sh
curl -X POST http://localhost:8000/team/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?"}'
```

**Expected:**
- New `session_id` generated (no previous context for lead)
- Lead may answer directly without delegating (simple question)
- Members are NOT disturbed if lead handles it solo

**Pass:** Lead answers directly. No member wakes. `done` event fires.

---

## Test 6 — Interrupt (via `/f` command)

Start a long task, then interrupt mid-stream:

**Step 1 — start long task:**
```sh
curl -X POST http://localhost:8000/team/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Research everything about climate change impacts on agriculture across all continents."}'
```

**Step 2 — wait 2-3 seconds, then interrupt via POST with `interrupt: true`:**

```sh
curl -X POST http://localhost:8000/team/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Stop. Focus only on Africa.", "interrupt": true}'
```

**Expected SSE events:**
```
... ongoing member events ...
event: agent_status     data: {"agent": "explorer", "status": "available"}     # cancel kicks in
event: agent_status     data: {"agent": "executor", "status": "available"}
event: agent_status     data: {"agent": "orchestrator", "status": "working"}      # lead activates with new instruction
event: message          data: {"agent": "orchestrator", "text": "Refocusing on Africa..."}
```

**Expected logs:**
```
INFO | team_interrupted name=task-force resetting_tasks=True
INFO | agent_streaming_interrupted agent=explorer
INFO | team_member_available name=explorer
INFO | team_member_activated name=orchestrator messages=...
```

**Key checks:**
- [ ] Working agents stop (agent_idle events appear for interrupted members)
- [ ] Non-completed tasks reset to pending (check logs for requeue if applicable)
- [ ] Lead wakes with the new "[user]: Stop. Focus only on Africa." message
- [ ] Lead re-plans and re-delegates with the narrowed scope
- [ ] A new `done` event fires when the redirected work completes

**Pass:** Team pivots cleanly to new instruction.
**Fail:** Agents hang after cancel, tasks stuck, lead never wakes.

---

## Test 7 — Member error recovery

This requires inducing a failure. Options:
- Temporarily break a tool (e.g. make `web_search` raise an exception)
- Kill the provider connection mid-stream

**Expected behaviour:**
- `_run_activation` catches the exception
- If member had claimed a task, it gets requeued (log: task requeue)
- Lead receives `[<member>]: [error: ...]` in its inbox
- Lead can reassign or surface the error
- `agent_status error` SSE event emitted for the failing member

**Pass:** Error surfaced to lead via inbox. Task requeued. No hang.
**Fail:** Member stuck `working`, lead never notified, or `done` never fires.

---

## Test 8 — Safety net (member forgets message_leader)

This tests the fallback when a member's LLM produces a final text response without calling `message_leader(stop=true)`.

Hard to trigger reliably. If it happens naturally, check logs for:
```
INFO | team_member_available name=explorer
```
And the lead should receive: `[explorer]: [done — no explicit reply]`

**Pass:** Lead still wakes and can proceed.

---

## Test 9 — Broadcast

Requires a scenario where the lead uses `broadcast()`. Send a message that would naturally prompt a team-wide update:

```sh
curl -X POST http://localhost:8000/team/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Change of plan: focus only on papers published after January 2026."}'
```

**Expected:**
- If members are working, lead may broadcast the update
- All members receive the broadcast (check SSE for both members waking)
- Broadcast does NOT go to the sender's own inbox (lead doesn't wake on its own broadcast)

**Pass:** Both members receive broadcast. Lead does not self-wake.

---

## Test 10 — Concurrent user messages (queue behaviour)

Send two messages rapidly without waiting for the first to complete:

```sh
curl -X POST http://localhost:8000/team/chat \
  -d '{"message": "Research topic A"}' &
curl -X POST http://localhost:8000/team/chat \
  -d '{"message": "Also research topic B"}'
```

**Expected:**
- Both messages land in lead's inbox
- Lead drains both on wake (log: `team_member_wake name=orchestrator messages=2`)
- Lead sees both and plans accordingly

**Pass:** Both messages processed, no lost messages.
**Fail:** Second message lost, or lead only sees one.

---

## Test 11 — Graceful shutdown

Stop the server with `Ctrl+C`.

**Expected logs:**
```
INFO | team_member_deregistered name=explorer
INFO | team_member_deregistered name=executor
INFO | team_member_deregistered name=consultant
INFO | team_member_deregistered name=orchestrator
INFO | agent_team_stopped name=task-force
INFO | server_shutdown
```

**Pass:** All agents exit cleanly within 5s. No hanging tasks.
**Fail:** Timeout on shutdown, or `CancelledError` stack traces.

---

## Test 12 — Session switch while streaming

Verify that switching to an old session while another is streaming does not leave the "..." processing indicator visible.

**Steps:**

1. Send a long-running prompt in session A (e.g. *"Write a detailed essay on…"*) so it streams for several seconds.
2. While the agent is actively streaming (cursor blinking / dots visible), click a **different, previously completed session** (session B) in the sidebar.

**Expected:**
- Session B renders immediately with its historical messages and **no** processing indicator.
- `isTeamWorking` in the Zustand store resets to `false` and all agent `status` fields read `"available"`.

**Verify via DevTools console (Redux DevTools extension or direct store access):**
```js
// After switching to session B:
useTeamStore.getState().isTeamWorking           // → false
useTeamStore.getState().agentStreams['lead'].status  // → "available"
```

**Fail:** "..." dots or streaming cursor remain visible in session B after the switch.

**Root cause / fix (resolved):** `loadSession` previously did not reset `isTeamWorking`, per-agent `status`, `currentText`, or `currentThinking` when loading a historical session. Fixed in `web/src/stores/useTeamStore/index.ts` — `loadSession` now unconditionally resets all streaming state before committing history. Regression tests: `useTeamStore.async.test.ts` → *"Regression: session-switch streaming indicator persists"*.

---

## Common failure patterns to watch for

| Symptom | Likely cause |
|---|---|
| `done` event never fires | A member stuck in `_run_activation()`, or lead crashed without becoming available |
| `done` fires before members finish | `_has_active_turn` guard missing or reset too early |
| Lead never activates | `session_id` not propagated — lead started fresh session |
| Member never activates | `send_message` targeted wrong name, or inbox not registered, or `on_message` callback missing |
| Duplicate task claims | `asyncio.Lock` not held during claim (check `_lock` usage) |
| SSE events missing | Queue full (512 limit) — events silently dropped |
| Shutdown hangs | `_active_task` cancellation timeout or `CancelledError` not caught |

---
