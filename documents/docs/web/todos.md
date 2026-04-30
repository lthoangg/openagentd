---
title: Todos Popover
description: Chat header popover showing the agent's current task list with live invalidation on tool_end.
status: stable
updated: 2026-04-24
---

# Todos popover

A popover card anchored to the **Todos** button in the team chat header. Shows
the agent's current task list as managed by `todo_manage`, sorted by status and
updated automatically after each `todo_manage` call.

---

## Opening the popover

| Trigger | Notes |
|---------|-------|
| **"Todos" button** in the chat header | Between the view toggles and the **Files** button; disabled when no session is active. |
| **`Ctrl+T`** | Keyboard shortcut registered in `useKeyboardShortcuts`. Disabled when no session is active. |
| **Command Palette** (`Ctrl+P`) | "Task List" entry under the **View** group. |

The popover is controlled (`open` / `onOpenChange`) so the keyboard shortcut
can toggle it programmatically. It is rendered via the shared `Popover` /
`PopoverContent` / `PopoverTrigger` primitives (`@base-ui/react/popover`).

---

## Data flow

### Query

`useTodosQuery(sessionId)` — thin TanStack Query hook over `getTodos(sessionId)`
(`GET /api/team/sessions/{id}/todos`). Query key: `queryKeys.todos(sessionId)`.
Enabled only when `sessionId` is set. `staleTime: 5_000`.

### Live invalidation

`useTeamStore` suppresses `tool_call`, `tool_start`, and `tool_end` SSE events
for `todo_manage` — no tool block is rendered in the chat. `tool_end` still
triggers a cache invalidation:

```ts
const TODO_MUTATING_TOOLS = new Set(['todo_manage'])

// tool_call / tool_start: early break — no block created
// tool_end: block completion skipped, invalidation still fires
if (TODO_MUTATING_TOOLS.has(toolName)) {
  const sid = useTeamStore.getState().sessionId
  if (sid) queryClient.invalidateQueries({ queryKey: queryKeys.todos(sid) })
}
```

### History reload

`assistantBlocks` in `src/utils/messages.ts` filters out `todo_manage` from
`msg.tool_calls` before creating blocks, so `todo_manage` calls are invisible
on page refresh too — both `parseTeamBlocks` (team history) and
`parseApiMessages` (single-agent history) go through this function.

---

## Display

Items are sorted before rendering: `in_progress → pending → completed → cancelled`.

| Status | Icon | Style |
|--------|------|-------|
| `in_progress` | `▶` | Normal text |
| `pending` | `○` | Normal text |
| `completed` | `✓` | Dimmed + strikethrough |
| `cancelled` | `✗` | Dimmed + strikethrough |

Priority badges:

| Priority | Color |
|----------|-------|
| `high` | Red tint |
| `medium` | Amber tint |
| `low` | Accent dim |

The popover header shows a `{done}/{total}` counter when the list is non-empty.
A dot indicator on the button itself is shown when any item has `status === 'in_progress'`.
Empty state: "No tasks yet".

The list is scrollable (`max-h-80 overflow-y-auto`) for long task lists.

---

## Backend

`GET /api/team/sessions/{session_id}/todos` reads `.todos.json` from
`workspace_dir(session_id)`. Returns `{todos: []}` when the file does not
exist. `session_id` must be a valid UUID (400 on malformed).

See [API reference — todo list](../api/index.md#todo-list) for the full contract.

---

## Related

- [API reference — todo list](../api/index.md#todo-list)
- [Agent tools — todo list](../agent/tools.md)
- [Workspace Files panel](./workspace-files.md) — same header, similar invalidation pattern
