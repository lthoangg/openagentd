/**
 * Rich tool result renderers.
 *
 * Each renderer receives the raw `result` string emitted by the backend and
 * the `toolName` so it can pick the right display strategy. Fall back to the
 * generic text view when nothing more specific applies.
 *
 * Visual language matches the `ToolCall` aside: no opaque dark fills, no
 * boxed-in containers. Results flow under the same left-rule indentation
 * as the args. When a code-like block is needed (file contents, shell
 * output), we use a quiet `--color-surface-2` tint and a thin border
 * rather than an overlay. Theme-aware, no hard-coded rgba.
 */

import { ExternalLink, Globe } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WebSearchResult {
  title?: string
  href?: string
  url?: string
  body?: string
  snippet?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tryParseJSON(raw: string): unknown | null {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/** Truncate a string to `max` chars, appending "…" if cut. */
function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max) + '…'
}

/** Best-effort hostname extraction without throwing. */
function hostname(href: string): string {
  try {
    return new URL(href).hostname.replace(/^www\./, '')
  } catch {
    return href
  }
}

// ---------------------------------------------------------------------------
// Web search result renderer
// ---------------------------------------------------------------------------

function WebSearchResult({ result }: { result: string }) {
  const parsed = tryParseJSON(result)

  // Normalise to array
  const items: WebSearchResult[] = Array.isArray(parsed)
    ? parsed
    : typeof parsed === 'object' && parsed !== null
      ? [parsed as WebSearchResult]
      : []

  if (items.length === 0) {
    return <GenericResult result={result} />
  }

  return (
    <ul className="space-y-2">
      {items.map((item, i) => {
        const link = item.href ?? item.url ?? ''
        const title = item.title ?? link
        const summary = item.body ?? item.snippet ?? ''

        return (
          <li key={i} className="group flex flex-col gap-0.5">
            {/* Title + link */}
            <div className="flex items-start gap-1.5">
              <Globe size={11} className="mt-0.5 shrink-0 text-(--color-info)" />
              {link ? (
                <a
                  href={link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 font-mono text-xs font-semibold leading-snug text-(--color-accent) underline-offset-2 hover:underline"
                >
                  {title}
                </a>
              ) : (
                <span className="flex-1 font-mono text-xs font-semibold leading-snug text-(--color-text)">
                  {title}
                </span>
              )}
            </div>

            {/* Hostname pill */}
            {link && (
              <div className="flex items-center gap-1 pl-5">
                <ExternalLink size={9} className="text-(--color-text-muted)" />
                <span className="font-mono text-[10px] text-(--color-text-muted)">
                  {hostname(link)}
                </span>
              </div>
            )}

            {/* Snippet */}
            {summary && (
              <p className="pl-5 font-mono text-[11px] leading-relaxed text-(--color-text-2)">
                {truncate(summary, 200)}
              </p>
            )}

            {/* Divider (not after last) */}
            {i < items.length - 1 && (
              <hr className="mt-1.5 border-t border-(--color-border)" />
            )}
          </li>
        )
      })}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Shell renderer
// ---------------------------------------------------------------------------

function ShellResult({ result }: { result: string }) {
  // First line is typically "[Succeeded]" or "[Failed — exit code N]"
  const firstNewline = result.indexOf('\n')
  const statusLine = firstNewline >= 0 ? result.slice(0, firstNewline).trim() : result.trim()
  const body = firstNewline >= 0 ? result.slice(firstNewline + 1).trimStart() : ''

  const success = statusLine.startsWith('[Succeeded')

  return (
    <div className="flex flex-col gap-1">
      {/* Status line — plain text, coloured by outcome */}
      <span
        className={`font-mono text-[11px] font-medium ${
          success ? 'text-(--color-success)' : 'text-(--color-error)'
        }`}
      >
        {statusLine}
      </span>

      {/* stdout / stderr output */}
      {body && (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-(--color-text-2)">
          {body}
        </pre>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Filesystem renderers
// ---------------------------------------------------------------------------

function FileListResult({ result }: { result: string }) {
  // ls / glob return newline-separated paths or JSON array
  const parsed = tryParseJSON(result)
  const entries: string[] = Array.isArray(parsed)
    ? parsed.map(String)
    : result
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)

  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[10px] text-(--color-text-muted)">
        {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
      </span>
      <ul className="max-h-64 overflow-auto space-y-0.5">
        {entries.map((e, i) => (
          <li key={i} className="font-mono text-[11px] leading-relaxed text-(--color-text-2)">
            {e}
          </li>
        ))}
      </ul>
    </div>
  )
}

function FileReadResult({ result }: { result: string }) {
  // Detect the optional "[start-end/total]" header emitted by read when a
  // range was requested. Promote it to a quiet metadata line so the pre
  // block shows only the actual file content.
  const match = result.match(/^\[(\d+)-(\d+)\/(\d+)\]\n([\s\S]*)$/)
  const rangeLabel = match ? `lines ${match[1]}–${match[2]} of ${match[3]}` : null
  const body = match ? match[4] : result

  return (
    <div className="flex flex-col gap-1">
      {rangeLabel && (
        <span className="font-mono text-[10px] text-(--color-text-muted)">{rangeLabel}</span>
      )}
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-(--color-text-2)">
        {body}
      </pre>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Team message renderer
// ---------------------------------------------------------------------------

function TeamMessageResult({ result }: { result: string }) {
  const isError =
    result.startsWith('Agent(s) not found') ||
    result.startsWith('No valid recipients')

  return (
    <span
      className={`font-mono text-[11px] leading-relaxed ${
        isError ? 'text-(--color-error)' : 'text-(--color-text-2)'
      }`}
    >
      {result}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Generic fallback renderer
// ---------------------------------------------------------------------------

function GenericResult({ result }: { result: string }) {
  // Try pretty-print if JSON
  const parsed = tryParseJSON(result)
  const display =
    parsed !== null && typeof parsed === 'object'
      ? JSON.stringify(parsed, null, 2)
      : result

  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-(--color-text-2)">
      {display}
    </pre>
  )
}

// ---------------------------------------------------------------------------
// Public dispatcher
// ---------------------------------------------------------------------------

const FILE_LIST_TOOLS = new Set(['ls', 'glob', 'grep'])
const FILE_READ_TOOLS = new Set(['read'])
const FILE_WRITE_TOOLS = new Set(['write', 'edit', 'rm'])
const SHELL_TOOLS = new Set(['shell'])
const WEB_SEARCH_TOOLS = new Set(['web_search'])
export function ToolResult({ toolName, result }: { toolName: string; result: string }) {
  if (WEB_SEARCH_TOOLS.has(toolName)) {
    return <WebSearchResult result={result} />
  }
  if (SHELL_TOOLS.has(toolName)) {
    return <ShellResult result={result} />
  }
  if (FILE_LIST_TOOLS.has(toolName)) {
    return <FileListResult result={result} />
  }
  if (FILE_READ_TOOLS.has(toolName)) {
    return <FileReadResult result={result} />
  }
  if (FILE_WRITE_TOOLS.has(toolName)) {
    // Write/edit results are usually short status messages — plain success style
    return <GenericResult result={result} />
  }
  if (toolName === 'team_message') {
    return <TeamMessageResult result={result} />
  }
  // web_fetch, date, math, skill, etc.
  return <GenericResult result={result} />
}
