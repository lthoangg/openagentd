/**
 * /settings/dream — edit dream.md: the dream agent's prompt and schedule.
 *
 * dream.md uses the same frontmatter format as regular agent files (parsed
 * by the same YAML loader), with two additional dream-specific fields:
 *   - enabled:  whether the scheduler fires automatically
 *   - schedule: cron expression (UTC)
 *
 * The page parses the file using the shared splitFrontmatter helper so the
 * block-style tools list (- item per line) is handled correctly — matching
 * what the backend's yaml.safe_load produces and consumes.
 *
 * A "Run now" button triggers POST /api/dream/run immediately.
 */
import { useMemo, useState } from 'react'
import { ArrowLeft, Moon, Play, Save } from 'lucide-react'
import { Link } from '@tanstack/react-router'

import {
  useDreamConfigQuery,
  useUpdateDreamConfigMutation,
  useTriggerDreamMutation,
} from '@/queries'
import { useToastStore } from '@/stores/useToastStore'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { splitFrontmatter } from '@/components/settings/frontmatter'

// ── Types ─────────────────────────────────────────────────────────────────────

interface DreamForm {
  // Agent fields
  name: string
  model: string
  tools: string[]
  // Dream-specific
  enabled: boolean
  schedule: string
}

const DEFAULT_FORM: DreamForm = {
  name: 'dream',
  model: '',
  tools: ['ls', 'read', 'wiki_search', 'write'],
  enabled: false,
  schedule: '0 2 * * *',
}

const DEFAULT_BODY = `You are the dream agent. Your job is to consolidate the wiki from unprocessed conversation sessions and notes.

Your working directory is the wiki root. Use relative paths directly:
- \`USER.md\` (not wiki/USER.md)
- \`topics/{slug}.md\` (not wiki/topics/)
- \`INDEX.md\` (not wiki/INDEX.md)

For each session/note you process:

1. Read \`USER.md\` — update it if new stable facts about the user were learned (identity, preferences, working style). Rewrite in-place, do not append.

2. For each topic that emerged: create or update \`topics/{slug}.md\` with required frontmatter:
   \`\`\`
   ---
   description: One-sentence summary (drives search relevance).
   tags: [tag1, tag2]
   updated: YYYY-MM-DD
   ---
   \`\`\`

3. Update \`INDEX.md\` — a table of contents listing all topic files with one-line descriptions.

Quality gate:
- Only promote durable facts worth remembering across sessions.
- Do not write noise, small talk, or one-off observations.
- If nothing worth promoting was found, do nothing.

Rules:
- Never delete existing topic files — only update them.
- Be surgical: only update sections that actually changed.
- Write precise, query-friendly descriptions for topics — they drive search relevance.`

// ── Parse / serialise ─────────────────────────────────────────────────────────

/**
 * Parse a raw dream.md string using the shared splitFrontmatter helper, then
 * walk the YAML lines to extract the form fields.  Uses the same block-list
 * format as agent .md files (- item per line).
 */
function parseDreamMd(raw: string): { form: DreamForm; body: string } {
  const { fm: fmText, body } = splitFrontmatter(raw)
  if (!fmText.trim()) return { form: { ...DEFAULT_FORM }, body: raw.trim() }

  const form = { ...DEFAULT_FORM }
  const lines = fmText.split('\n')
  let inTools = false
  const tools: string[] = []

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, '')
    if (!line.trim() || line.trim().startsWith('#')) continue

    // Block-list item under tools:
    const listMatch = /^\s+-\s+(.+)$/.exec(line)
    if (inTools && listMatch) {
      tools.push(listMatch[1].trim())
      continue
    }
    inTools = false

    const kvMatch = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line)
    if (!kvMatch) continue
    const [, key, rawVal] = kvMatch
    const val = rawVal.trim().replace(/#.*$/, '').trim().replace(/^["']|["']$/g, '')

    switch (key) {
      case 'name':    form.name = val; break
      case 'model':   form.model = val; break
      case 'enabled': form.enabled = val === 'true'; break
      case 'schedule': form.schedule = val; break
      case 'tools':
        // tools: (empty → block list follows)
        if (!val) { inTools = true }
        break
    }
  }

  if (tools.length > 0) form.tools = tools

  return { form, body: body.trim() }
}

/**
 * Serialise form fields back to canonical dream.md format:
 * - Uses block-style YAML lists (- item) matching the backend parser
 * - Tools sorted alphabetically (stable diffs)
 * - dream-specific fields (enabled, schedule) after agent fields
 */
function serialiseDreamMd(form: DreamForm, body: string): string {
  const lines: string[] = []
  lines.push(`name: ${form.name}`)
  lines.push('role: member')
  if (form.model) lines.push(`model: ${form.model}`)
  lines.push(`enabled: ${form.enabled}`)
  lines.push(`schedule: "${form.schedule}"`)
  if (form.tools.length > 0) {
    lines.push('tools:')
    for (const t of [...form.tools].sort()) lines.push(`  - ${t}`)
  }
  return `---\n${lines.join('\n')}\n---\n\n${body.trim()}\n`
}

// ── Page component ────────────────────────────────────────────────────────────

export function DreamSettingsPage() {
  const isMobile = useIsMobile()
  const { data, isLoading, error } = useDreamConfigQuery()
  const updateMut = useUpdateDreamConfigMutation()
  const dreamMut = useTriggerDreamMutation()
  const push = useToastStore((s) => s.push)

  const [form, setForm] = useState<DreamForm>(DEFAULT_FORM)
  const [body, setBody] = useState(DEFAULT_BODY)
  const [sourceRaw, setSourceRaw] = useState('')

  // Rebase form onto server data when it changes (snapshot identity pattern)
  const serverRaw = data?.content ?? ''
  if (serverRaw !== sourceRaw) {
    const parsed = parseDreamMd(serverRaw)
    setForm(parsed.form)
    setBody(parsed.body)
    setSourceRaw(serverRaw)
  }

  const currentRaw = useMemo(() => serialiseDreamMd(form, body), [form, body])
  const dirty = currentRaw !== sourceRaw

  const handleSave = async () => {
    try {
      await updateMut.mutateAsync(currentRaw)
      setSourceRaw(currentRaw)
      push({ tone: 'success', title: 'Dream config saved' })
    } catch (err) {
      push({
        tone: 'error',
        title: 'Save failed',
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  const handleRunNow = async () => {
    try {
      const result = await dreamMut.mutateAsync()
      push({
        tone: 'success',
        title: 'Dream run complete',
        description: `${result.sessions_processed} sessions, ${result.notes_processed} notes processed.`,
      })
    } catch (err) {
      push({
        tone: 'error',
        title: 'Dream run failed',
        description: err instanceof Error ? err.message : String(err),
      })
    }
  }

  const setField = <K extends keyof DreamForm>(key: K, val: DreamForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: val }))

  // Tools displayed as a comma-separated string in the input
  const toolsStr = form.tools.join(', ')
  const setTools = (raw: string) =>
    setField('tools', raw.split(',').map((s) => s.trim()).filter(Boolean))

  return (
    <>
      <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4">
        {isMobile && (
          <Link
            to="/settings"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label="Back to settings"
          >
            <ArrowLeft size={14} />
          </Link>
        )}
        <Moon size={15} className="shrink-0 text-muted-foreground" aria-hidden="true" />
        <h1 className="flex-1 truncate text-sm font-semibold">Dream</h1>
        {dirty && (
          <span className="text-xs text-muted-foreground" aria-live="polite">
            Unsaved
          </span>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={handleRunNow}
          disabled={dreamMut.isPending}
        >
          <Play size={12} aria-hidden="true" />
          {dreamMut.isPending ? 'Running…' : 'Run now'}
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!dirty || updateMut.isPending}
        >
          <Save size={12} aria-hidden="true" />
          {updateMut.isPending ? 'Saving…' : 'Save'}
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-6 p-6">
          <p className="text-sm leading-relaxed text-muted-foreground">
            The dream agent runs on a cron schedule and synthesises unprocessed conversation
            sessions and notes into wiki topics. Configure its schedule, model, and system prompt
            below, or click <strong>Run now</strong> to trigger it immediately.
          </p>

          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {error && (
            <p className="text-sm text-destructive">
              {error instanceof Error ? error.message : String(error)}
            </p>
          )}

          {!isLoading && !error && (
            <div className="space-y-5">
              {/* ── Schedule ────────────────────────────────────── */}
              <section className="space-y-3 rounded-xl border border-border p-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Schedule
                </h2>

                <div className="flex items-center gap-3">
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.enabled}
                      onChange={(e) => setField('enabled', e.target.checked)}
                      className="h-4 w-4 rounded border-border accent-foreground"
                    />
                    Enabled
                  </label>
                  <span className="text-xs text-muted-foreground">
                    When disabled, dream runs only via <em>Run now</em> or <code className="font-mono">/dream</code>.
                  </span>
                </div>

                <div className="grid gap-1.5">
                  <label htmlFor="dream-schedule" className="text-xs font-medium text-muted-foreground">
                    Cron expression
                  </label>
                  <Input
                    id="dream-schedule"
                    value={form.schedule}
                    onChange={(e) => setField('schedule', e.target.value)}
                    placeholder="0 2 * * *"
                    className="h-9 font-mono text-sm"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Standard 5-field cron (UTC). Example: <code className="font-mono">0 2 * * *</code> = daily at 2 AM.
                  </p>
                </div>
              </section>

              {/* ── Model ───────────────────────────────────────── */}
              <section className="space-y-3 rounded-xl border border-border p-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Model
                </h2>

                <div className="grid gap-1.5">
                  <label htmlFor="dream-model" className="text-xs font-medium text-muted-foreground">
                    Model ID
                  </label>
                  <Input
                    id="dream-model"
                    value={form.model}
                    onChange={(e) => setField('model', e.target.value)}
                    placeholder="googlegenai:gemini-2.0-flash"
                    className="h-9 font-mono text-sm"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Format: <code className="font-mono">provider:model-name</code>. Leave empty to skip LLM synthesis (infrastructure-only mode).
                  </p>
                </div>

                <div className="grid gap-1.5">
                  <label htmlFor="dream-tools" className="text-xs font-medium text-muted-foreground">
                    Extra tools (comma-separated)
                  </label>
                  <Input
                    id="dream-tools"
                    value={toolsStr}
                    onChange={(e) => setTools(e.target.value)}
                    placeholder="ls, read, wiki_search, write"
                    className="h-9 font-mono text-sm"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    <code className="font-mono">read, write, ls, wiki_search</code> are always injected by the backend regardless of this list.
                  </p>
                </div>
              </section>

              {/* ── Prompt ──────────────────────────────────────── */}
              <section className="space-y-3 rounded-xl border border-border p-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  System prompt
                </h2>

                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={20}
                  spellCheck={false}
                  className="w-full resize-y rounded-lg border border-border bg-background px-3 py-2.5 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring/40"
                  placeholder={DEFAULT_BODY}
                />
                <p className="text-[11px] text-muted-foreground">
                  The dream agent receives each unprocessed session transcript and note as user messages. This prompt sets its behaviour and quality gates.
                </p>
              </section>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
