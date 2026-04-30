---
title: Tool Call & Result Rendering
description: Aside-style tool cards with status dots, per-tool headers, expandable args/result panels, custom renderers.
status: stable
updated: 2026-04-21
---

# Tool Call & Result Rendering

Aside-style rendering for `ToolCall` blocks: a quiet left-rule margin note with an optional per-tool header, italicised argument values, an expandable args/result panel, and tool-aware result renderers.

---

## Overview

Each tool call renders as a collapsible aside in `ToolCall.tsx`. Visual language mirrors `Thinking.tsx` — no card, no background on the row itself, no tool-type icon. Identity is carried by a **colored status dot** (matching the `AgentCapabilities` vocabulary) plus a tool-specific one-line summary (header) or the bare tool name as a fallback.

The **header** and **arguments** section are customised per tool via `getToolDisplay()`. The **result** section is rendered by `ToolResult.tsx`, which picks a renderer based on `toolName`.

**Spacing:** `ToolCall` does not set its own inter-block spacing — that is owned by the parent container (`space-y-1` / `space-y-1.5` / `space-y-2` depending on the view).

```
ToolCall.tsx                        (aside row + header + expand/collapse)
  ├── StatusDot                     (6px dot — pending / running / done)
  ├── Arg                           (italicises argument values in headers)
  ├── getToolDisplay()              (per-tool header ReactNode & args formatting)
  └── ToolResult.tsx                (result section dispatcher)
        ├── WebSearchResult         — web_search
        ├── ShellResult             — shell
        ├── FileListResult          — ls, glob, grep
        ├── FileReadResult          — read
        ├── TeamMessageResult       — team_message
        └── GenericResult           — everything else (bg, web_fetch, date,
                                       write, edit, rm, skill, math, …)
```

---

## Header row

The collapsed header is a single flex row:

```
[chevron] [●] Reading example.com                   [pending?]
```

- **Chevron** (`ChevronRight`, 12px, `--color-text-muted`) — rendered only when the block has expandable details; rotates 90° when expanded. Absent for tools with no args and no result (e.g. `date`, `skill`).
- **Status dot** — 6px round, `shrink-0`. One of:
  | State | Condition | Dot style |
  |-------|-----------|-----------|
  | `pending` | `args === undefined` | `bg-(--color-text-muted)` |
  | `running` | args set, `done === false` | `bg-(--color-accent)` + pulse + glow shadow |
  | `done` | `done === true` | `bg-(--color-success)` |
- **Header content** — either a per-tool `ReactNode` (built by `getToolDisplay()`) rendered inside a `truncate` span, or the raw tool name rendered as a `<code>` element when no custom header exists.
- **`pending` text** (optional) — appears at the right when the call has no args yet.

The whole row is a `<button>` so the entire strip is the click target — no separate "click here to expand" affordance.

### Italicised argument values (`<Arg>`)

Inside the header, only the **argument value** is italicised — the verb/framing text stays upright. This is handled by the `<Arg>` helper, which wraps its children in `<em class="italic">`. For example:

```tsx
// header produced for `read`:
<>Reading <Arg>agent_loop.py</Arg></>
// renders as: Reading <em>agent_loop.py</em>
```

Every custom header case returns both a `ReactNode` (for display) and a plain-string `headerTitle` (used for the `title="…"` tooltip when the header is truncated, and for `aria-label`). HTML attributes can't accept ReactNodes, hence the parallel string.

### Expandable details panel

When expanded, the args and/or result sections slide open below the header. Each section has:

- A caption (`arguments` / `bash` / `result`) in uppercase 10px tracked text (`--color-text-subtle`) and an inline copy button on the right.
- A **subtle surface panel** wrapping the content: `rounded-md`, `border border-(--color-border)`, `bg-(--color-surface-2)`, `px-2.5 py-2`. This restores readability for long arg/result blobs without reverting to the heavy `rgba(0,0,0,0.25)` overlay the redesign removed. `--color-surface-2` is the same token shadcn uses for `--card` / `--muted`, so it auto-themes in light/dark.

---

## Custom ToolCall display

**File:** `web/src/components/ToolCall.tsx` — `getToolDisplay(name, args) → ToolDisplay`

```ts
interface ToolDisplay {
  header: ReactNode | null       // JSX with <Arg> around the argument value;
                                 // null = fall back to tool name
  headerTitle: string | null     // plain-string mirror for title + aria-label
  formattedArgs: string | null   // simplified args body; null = hide args section
  language?: 'bash' | null       // 'bash' → render formattedArgs as a code block
  suppressResult?: boolean       // true → hide the result section entirely
                                 // (used by `generate_image` / `generate_video`,
                                 //  whose result markdown is already rendered
                                 //  inline in the assistant reply)
}
```

Verbs are **deterministic** (no randomised phrase pools). Only argument values shown in brackets below are italicised via `<Arg>`.

| Tool | Header | Expanded args | Args label |
|------|--------|---------------|------------|
| `date` | tool name | hidden | — |
| `shell` | *[description]* (falls back to tool name if empty) | command string as bash block with non-selectable `$ ` prefix | `bash` |
| `web_search` | Searching *["query"]* | query string | `arguments` |
| `web_fetch` | Reading *[domain]* (`www.` stripped) | full URL | `arguments` |
| `write` | Writing *[filename]* | file content only (no JSON wrapper) | `arguments` |
| `read` | Reading *[filename]* — range suffix ` [start:end]` when `offset`/`limit` set | hidden | — |
| `edit` | Editing *[filename]* | full JSON (`path`, `old_string`, `new_string`, `replace_all`) | `arguments` |
| `rm` | Removing *[filename]* | hidden | — |
| `ls` | `Listing workspace` (default path) or `Listing` *[path]* | hidden | — |
| `glob` | Finding *[pattern]* ` in {dir}` ` (by name)` (optional suffixes) | `pattern: …` / `directory: …` / `match: …` lines when non-default | `arguments` |
| `grep` | Searching *[pattern]* ` in {dir}` ` ({include})` (optional suffixes) | `pattern: …` / `directory: …` / `include: …` lines when non-default | `arguments` |
| `remember` | `Saving to memory…` | `[category] key: value` per item | `arguments` |
| `forget` | `Removing from memory…` | `category: key` per item | `arguments` |
| `recall` | `Checking memory…` | `category: key` filter, or hidden if empty | `arguments` |
| `skill` | `Loading skill: `*[skill_name]* (or `Loading skill…`) | hidden | — |
| `bg` | Action-based — e.g. `Listing background processes…`, `Checking process `*[pid]*`…`, `Reading output of process `*[pid]*`…`, `Stopping process `*[pid]*`…`, `Managing background process…` | hidden | — |
| `team_message` | Messaging *[recipients]* (joined by `, `, truncated at 60 chars) | message `content` only (no JSON wrapper) | `arguments` |
| `generate_image` | Painting *[filename]* (normalised: any trailing extension stripped, `.png` appended to match the backend `_sanitise_filename`), or `Painting an image…` when filename is absent | `prompt` string only (`images: …` line prepended in edit mode) | `arguments` |
| `generate_video` | Filming *[filename]* (`.mp4` appended; random `video-<hex>` when absent), or `Filming a video…` when filename is absent | `first_frame` / `last_frame` / `references` input lines (when set) prepended to the `prompt` | `arguments` |

> Both `generate_image` and `generate_video` set `suppressResult: true` — their markdown return values (`![prompt](file.png)` / `![prompt](file.mp4)`) are already rendered inline in the assistant reply, so the tool-call accordion does not repeat them. The `.mp4` path is rendered as `<video controls>` by `MarkdownVideo` (see [`docs/agent/tools.md#multimodalities-multimodalities`](../agent/tools.md#multimodalities-multimodalities)).

All other tools use the default: tool name as `<code>` header, pretty-printed JSON as args, label `arguments`. Tools called with an empty `{}` args object hide the args section and are not expandable.

---

## Component: `ToolResult`

**File:** `web/src/components/ToolResult.tsx`

```tsx
<ToolResult toolName={name} result={result} />
```

| Prop | Type | Description |
|------|------|-------------|
| `toolName` | `string` | Tool name — used for renderer dispatch |
| `result` | `string` | Raw result string from the backend |

The renderer is always rendered inside the surface panel described above, so individual renderers focus on **content**, not on chrome. The redesign dropped all per-renderer overlays, redundant icons, and captions (e.g. the old `FileText`-headed `file content` caption is gone — the outer `result` caption already identifies the section).

---

## Result renderers

### `WebSearchResult` — `web_search`

Backend returns `list[dict]` with `{title, href, body}` per result. The renderer:

- Parses JSON; falls back to `GenericResult` if not a valid array.
- Each item renders:
  - **Title** as a clickable `<a>` link (opens in new tab, `rel="noopener noreferrer"`).
  - **Hostname pill** — extracted via `new URL(href).hostname`, `www.` stripped.
  - **Snippet** — `body` truncated to 200 chars.
- Items separated by `<hr>`.

### `ShellResult` — `shell`

Backend returns one of:
- **Foreground:** `"[Succeeded]\n\n<stdout>"` or `"[Failed — exit code N]\n\n<stdout+stderr>"`

Rendering:
- First line is parsed as the status token. `Succeeded` uses `--color-success`; `Failed …` uses `--color-error`. No boxed chrome, no icons.
- Remaining output in a scrollable `<pre>` (`max-h-48`, `break-words`).

> `bg` results are no longer rendered by `ShellResult`. They fall through to `GenericResult` because `bg` returns free-form management text (`PID <pid>: running`, `stopped (exit code N)\nFinal output:\n…`) that does not share the foreground `[Succeeded]` / `[Failed]` header convention.

### `FileListResult` — `ls`, `glob`, `grep`

- Tries JSON array parse; falls back to splitting on newlines and trimming each line.
- Shows an entry-count metadata line (`N entries`).
- Lists entries in a scrollable `<ul>` (`max-h-64`) in monospace.

> Known limitation: `ls`'s line format (`[d] name/` / `[f] name  (123 bytes)`) and the empty-state strings from each backend tool (`(empty directory)`, `No files matching…`, `No matches for pattern…`) are rendered verbatim. Richer per-marker rendering is tracked as follow-up work.

### `FileReadResult` — `read`

- Detects the optional `[start-end/total]\n` prefix emitted by the backend when `offset`/`limit` were used and promotes it to a quiet `lines N–M of T` metadata line above the content.
- Content rendered in a scrollable `<pre>` (`max-h-80`, `whitespace-pre-wrap`, `break-words`).
- No `FileText` icon, no `file content` caption (the outer `result` caption already marks the section).

### `TeamMessageResult` — `team_message`

Backend returns one of:
- **Success:** `"Message sent to {recipient1}, {recipient2}."` — rendered in `--color-text-2`.
- **Error:** `"Agent(s) not found: {name}. Available: {others}"` or `"No valid recipients…"` — rendered in `--color-error`.

Plain monospace text, no icon. All colors are theme tokens — no raw Tailwind palette names.

### `GenericResult` — everything else

- If `result` parses as a JSON **object**, pretty-prints with `JSON.stringify(parsed, null, 2)`.
- Otherwise renders as-is in a monospace `<pre>` (`max-h-64`, `break-words`).
- Default text color is `--color-text-2` — not `--color-success`. (Previously this renderer defaulted to green, which made every unrelated result — `write`, `edit`, `date`, `skill`, … — look "successful" even when the tool had no notion of success/failure.)

---

## Copy buttons

Both the **arguments** section and the **result** section have independent copy-to-clipboard buttons (`aria-label="Copy arguments"` / `aria-label="Copy result"`). Each uses its own boolean state (`copiedArgs` / `copiedResult`) and flips to a green check for 1.5 s after a successful copy.

The args copy button copies `formattedArgs` — the extracted, human-readable value — not the raw JSON string. For example, copying a `shell` tool call copies the bare command (`date`) rather than the full input object (`{"command":"date","description":"..."}`). If `formattedArgs` is null, it falls back to the raw `args` string.

---

## Adding a new renderer

1. Add a helper function (e.g. `function MyToolResult(...)`) in `ToolResult.tsx`. Keep it chrome-free — the outer panel is provided by `ToolCall`.
2. Add the tool name(s) to a `Set` constant at the top of the dispatcher section.
3. Add a branch in `ToolResult` before the final `GenericResult` fallback.
4. Add tests in `web/src/__tests__/components/ToolResult.test.tsx`.

## Adding a custom header

1. Add a branch in `getToolDisplay()` before the default fallback.
2. Return `header` as a `ReactNode` — wrap every argument value in `<Arg>` so it gets italicised. Keep verbs/framing upright.
3. Return `headerTitle` as the plain-string mirror (used by `title` and `aria-label`). The two strings should match once you strip `<em>` tags.
4. Decide on `formattedArgs`:
   - `null` → hide the args section entirely (use this when the header already carries all the useful info and no args panel would add value).
   - A short human-readable string (e.g. just the query, just the filename) → shown as-is.
   - `language: 'bash'` → also render the string as a bash code block with a `$ ` prefix.
5. Add tests in `web/src/__tests__/components/ToolCall.test.tsx`. Use the `getHeader(fullText)` + `expectItalicArg(header, arg)` helpers so assertions survive the `<span>verb <em>arg</em></span>` split.
