/**
 * AgentForm — hybrid form for agent .md files.
 *
 * Modes:
 *   - **form**: structured fields for frontmatter + textarea for the
 *     system prompt body. Changes are serialised to canonical YAML on
 *     save. Recommended for most users.
 *   - **raw**: plain textarea with the full .md contents (frontmatter +
 *     body). Power users can hand-edit nested fields the form doesn't
 *     model (e.g. summarization blocks, custom hooks).
 *
 * Switching form → raw preserves any extra YAML fields the form doesn't
 * know about by re-using the previous raw content whenever possible.
 * Switching raw → form re-parses the current raw text.
 *
 * The mode is a controlled prop so the editor's sticky header (rendered
 * by the parent route) hosts the Form/Raw toggle next to Save — keeping
 * top-of-page real estate consistent across all editor pages.
 */
import { useMemo, useState } from 'react'
import { AlertCircle } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { useMcpServersQuery, useRegistryQuery } from '@/queries'
import { MultiSelect, type MultiSelectOption } from './MultiSelect'
import { combine, splitFrontmatter, type AgentFrontmatter } from './frontmatter'
import {
  parseTemperatureInput,
  validateAgentName,
  validateDescription,
  validateModel,
} from './schema'

export interface AgentFormValue {
  /** Current raw .md content (frontmatter + body). Always authoritative. */
  raw: string
}

interface Props {
  initial: string
  /** Fires on every keystroke with the up-to-date raw content. */
  onChange: (raw: string) => void
  /** Disabled when the caller is mid-save / validation. */
  disabled?: boolean
  /** When creating a new agent the name is still editable. */
  isNew?: boolean
  /** Controlled Form/Raw mode — owned by the parent so the sub-header
   *  toggle stays in sync with the form body. */
  mode: 'form' | 'raw'
  onModeChange: (next: 'form' | 'raw') => void
}

const THINKING_LEVELS: Array<{ value: string; label: string }> = [
  { value: '__none__', label: '(default)' },
  { value: 'none', label: 'none' },
  { value: 'low', label: 'low' },
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
]

export function AgentForm({
  initial,
  onChange,
  disabled,
  isNew,
  mode,
  onModeChange,
}: Props) {
  const [raw, setRaw] = useState(initial)

  // Seed form state from the initial raw content. Subsequent edits update
  // `raw` via `updateFromForm` / `updateFromRaw` — never from `initial`.
  const seed = useMemo(() => parseFormState(initial), [initial])
  const [fm, setFm] = useState<AgentFrontmatter>(seed.fm)
  const [body, setBody] = useState(seed.body)
  const [parseError, setParseError] = useState<string | null>(seed.error)

  // If the parent swaps `initial` (e.g. navigating between agents), adopt
  // the new seed. We track the last-seen initial in state so this is a
  // plain derived-state update rather than an effect.
  const [lastInitial, setLastInitial] = useState(initial)
  if (initial !== lastInitial) {
    setLastInitial(initial)
    setRaw(initial)
    setFm(seed.fm)
    setBody(seed.body)
    setParseError(seed.error)
  }

  // When the parent flips mode, re-parse if going back to form so we don't
  // show stale field values.
  const [lastMode, setLastMode] = useState(mode)
  if (mode !== lastMode) {
    setLastMode(mode)
    if (mode === 'form') {
      const p = parseFormState(raw)
      setFm(p.fm)
      setBody(p.body)
      setParseError(p.error)
    }
  }

  const registry = useRegistryQuery()
  const mcpServers = useMcpServersQuery()

  // Hide ``mcp_<server>_<tool>`` entries from the Tools picker — they are
  // granted en bloc via the MCP server picker below, so showing them in
  // both places would let the user pick the same capability twice.
  const toolOptions: MultiSelectOption[] =
    registry.data?.tools
      .filter((t) => !t.name.startsWith('mcp_'))
      .map((t) => ({
        value: t.name,
        label: t.name,
        description: t.description,
      })) ?? []

  const skillOptions: MultiSelectOption[] =
    registry.data?.skills.map((s) => ({
      value: s.name,
      label: s.name,
      description: s.description,
    })) ?? []

  // Show every server, including disabled / errored ones, so an agent can
  // still reference a server that's temporarily down without the picker
  // silently dropping the chip on save.
  const mcpOptions: MultiSelectOption[] =
    mcpServers.data?.servers.map((s) => {
      const tools = s.tool_names.length
      const detail = `${s.transport} \u00b7 ${s.state} \u00b7 ${tools} tool${tools === 1 ? '' : 's'}`
      return {
        value: s.name,
        label: s.name,
        description: detail,
      }
    }) ?? []

  const modelOptions = registry.data?.models ?? []

  // Form → raw propagation. Runs whenever a form field changes.
  const updateFromForm = (next: AgentFrontmatter, nextBody: string) => {
    setFm(next)
    setBody(nextBody)
    const r = combine(next, nextBody)
    setRaw(r)
    onChange(r)
    setParseError(null)
  }

  // Raw → form propagation. Parsing may fail; we surface the error but
  // still let the user fix it in raw mode.
  const updateFromRaw = (nextRaw: string) => {
    setRaw(nextRaw)
    onChange(nextRaw)
    const p = parseFormState(nextRaw)
    setFm(p.fm)
    setBody(p.body)
    setParseError(p.error)
  }

  return (
    <div className="flex flex-col gap-4">
      {parseError && (
        <ParseErrorBanner
          message={parseError}
          onSwitchToRaw={() => onModeChange('raw')}
        />
      )}

      {mode === 'form' ? (
        <FormFields
          fm={fm}
          body={body}
          disabled={disabled}
          isNew={isNew}
          toolOptions={toolOptions}
          skillOptions={skillOptions}
          mcpOptions={mcpOptions}
          modelOptions={modelOptions}
          updateFromForm={updateFromForm}
        />
      ) : (
        <Card size="sm">
          <CardHeader>
            <CardTitle>Raw .md</CardTitle>
            <CardDescription>
              Edit the raw frontmatter and body. Useful for fields the form
              doesn&rsquo;t expose (e.g. nested summarization blocks).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea
              value={raw}
              onChange={(e) => updateFromRaw(e.target.value)}
              disabled={disabled}
              rows={28}
              spellCheck={false}
              className="font-mono text-[13px] leading-relaxed"
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ParseErrorBanner({
  message,
  onSwitchToRaw,
}: {
  message: string
  onSwitchToRaw: () => void
}) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
      <AlertCircle size={14} className="mt-0.5 shrink-0" />
      <div className="flex-1">
        <p className="font-medium">Parse error</p>
        <p className="mt-0.5 opacity-90">{message}</p>
      </div>
      <Button size="xs" variant="outline" onClick={onSwitchToRaw}>
        Open raw
      </Button>
    </div>
  )
}

// ── Form mode ───────────────────────────────────────────────────────────────

/**
 * The Form-mode UI, organised into Cards so each concern has a clear title
 * and the form scans top-to-bottom: who → what model → behaviour → tools
 * & skills → system prompt.
 */
function FormFields({
  fm,
  body,
  disabled,
  isNew,
  toolOptions,
  skillOptions,
  mcpOptions,
  modelOptions,
  updateFromForm,
}: {
  fm: AgentFrontmatter
  body: string
  disabled?: boolean
  isNew?: boolean
  toolOptions: MultiSelectOption[]
  skillOptions: MultiSelectOption[]
  mcpOptions: MultiSelectOption[]
  modelOptions: { id: string; provider: string; model: string; vision: boolean }[]
  updateFromForm: (next: AgentFrontmatter, nextBody: string) => void
}) {
  // Temperature has a pending state (e.g. "0." while typing) that we need
  // to preserve as a string in local state, independent of the committed
  // `fm.temperature` number. Same approach as React's controlled-input
  // guidance for numeric fields.
  const [tempRaw, setTempRaw] = useState<string>(
    fm.temperature == null ? '' : String(fm.temperature),
  )
  const [tempError, setTempError] = useState<string | null>(null)

  // Per-field errors computed fresh from zod on render. For the scalar
  // string fields we validate whenever the value is non-empty; empty is
  // handled by the caller's full-form check before save.
  const nameError = isNew ? validateAgentName(fm.name) : null
  const descriptionError = validateDescription(fm.description ?? '')
  const modelError = validateModel(fm.model ?? '', { required: true })
  const fallbackError = validateModel(fm.fallback_model ?? '')

  const onTempChange = (next: string) => {
    setTempRaw(next)
    const parsed = parseTemperatureInput(next)
    if (parsed.ok === true) {
      setTempError(null)
      updateFromForm({ ...fm, temperature: parsed.value }, body)
    } else if (parsed.ok === 'pending') {
      setTempError(null)
      // Do NOT push to fm yet — keep the last committed value so we don't
      // flip dirty flags spuriously while the user is mid-typing.
    } else {
      setTempError(parsed.error)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Identity ─────────────────────────────────────────────── */}
      <Card size="sm">
        <CardHeader>
          <CardTitle>Identity</CardTitle>
          <CardDescription>Who is this agent and what is its role?</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field
            label="Name"
            required
            error={nameError}
            hint={
              !isNew
                ? 'Filename stem; cannot be renamed after creation.'
                : 'Letters, digits, ., _, - only.'
            }
          >
            <Input
              type="text"
              value={fm.name}
              onChange={(e) => updateFromForm({ ...fm, name: e.target.value }, body)}
              disabled={disabled || !isNew}
              placeholder="orchestrator"
              aria-invalid={!!nameError || undefined}
              className="font-mono"
            />
          </Field>

          <Field label="Role" required hint="Exactly one agent in the team must be lead.">
            <Select
              value={fm.role}
              onValueChange={(v) =>
                v && updateFromForm({ ...fm, role: v as 'lead' | 'member' }, body)
              }
              disabled={disabled}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="lead">Lead</SelectItem>
                <SelectItem value="member">Member</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field
            label="Description"
            error={descriptionError}
            className="md:col-span-2"
            hint="One-line summary shown when the lead browses the team."
          >
            <Input
              type="text"
              value={fm.description ?? ''}
              onChange={(e) =>
                updateFromForm({ ...fm, description: e.target.value || null }, body)
              }
              disabled={disabled}
              placeholder="Coordinates the team. Breaks tasks, delegates to members."
              aria-invalid={!!descriptionError || undefined}
            />
          </Field>
        </CardContent>
      </Card>

      {/* Model & behaviour ─────────────────────────────────────── */}
      <Card size="sm">
        <CardHeader>
          <CardTitle>Model &amp; behaviour</CardTitle>
          <CardDescription>
            Which provider, plus sampling temperature and reasoning depth.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Model" required error={modelError} className="md:col-span-2">
            <ModelPicker
              value={fm.model ?? ''}
              options={modelOptions}
              onChange={(v) => updateFromForm({ ...fm, model: v }, body)}
              disabled={disabled}
              invalid={!!modelError}
            />
          </Field>

          <Field
            label="Fallback model"
            error={fallbackError}
            hint="Used when the primary model errors out."
            className="md:col-span-2"
          >
            <ModelPicker
              value={fm.fallback_model ?? ''}
              options={modelOptions}
              allowEmpty
              onChange={(v) => updateFromForm({ ...fm, fallback_model: v || null }, body)}
              disabled={disabled}
              invalid={!!fallbackError}
            />
          </Field>

          <Field label="Temperature" error={tempError} hint="0 – 2; higher = more random.">
            <Input
              type="text"
              inputMode="decimal"
              value={tempRaw}
              onChange={(e) => onTempChange(e.target.value)}
              disabled={disabled}
              placeholder="0.2"
              aria-invalid={!!tempError || undefined}
              className="font-mono"
            />
          </Field>

          <Field label="Thinking level" hint="How much hidden reasoning the model may use.">
            <Select
              value={fm.thinking_level ? fm.thinking_level : '__none__'}
              onValueChange={(v) => {
                if (v == null) return
                updateFromForm(
                  { ...fm, thinking_level: v === '__none__' ? null : v },
                  body,
                )
              }}
              disabled={disabled}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {THINKING_LEVELS.map((lvl) => (
                  <SelectItem key={lvl.value} value={lvl.value}>
                    {lvl.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </CardContent>
      </Card>

      {/* Capabilities ──────────────────────────────────────────── */}
      <Card size="sm">
        <CardHeader>
          <CardTitle>Capabilities</CardTitle>
          <CardDescription>
            Tools the agent may invoke, MCP servers it has access to, and
            skills it can load on demand.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Field
            label="Tools"
            hint={`${(fm.tools ?? []).length} selected of ${toolOptions.length} available.`}
          >
            <MultiSelect
              options={toolOptions}
              value={fm.tools ?? []}
              onChange={(v) => updateFromForm({ ...fm, tools: v }, body)}
              placeholder="Pick tools this agent may invoke…"
            />
          </Field>

          <Field
            label="MCP servers"
            hint={
              mcpOptions.length === 0
                ? 'No MCP servers configured. Add one under Settings → MCP.'
                : `${(fm.mcp ?? []).length} selected of ${mcpOptions.length} available. Each grants every tool the server exposes.`
            }
          >
            <MultiSelect
              options={mcpOptions}
              value={fm.mcp ?? []}
              onChange={(v) => updateFromForm({ ...fm, mcp: v }, body)}
              placeholder="Pick MCP servers this agent may use…"
              emptyLabel="No matching servers"
            />
          </Field>

          <Field
            label="Skills"
            hint={`${(fm.skills ?? []).length} selected of ${skillOptions.length} available.`}
          >
            <MultiSelect
              options={skillOptions}
              value={fm.skills ?? []}
              onChange={(v) => updateFromForm({ ...fm, skills: v }, body)}
              placeholder="Pick skills the agent can load on demand…"
            />
          </Field>
        </CardContent>
      </Card>

      {/* System prompt ─────────────────────────────────────────── */}
      <Card size="sm">
        <CardHeader>
          <CardTitle>System prompt</CardTitle>
          <CardDescription>
            The instructions placed at the top of every conversation with this agent.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea
            value={body}
            onChange={(e) => updateFromForm(fm, e.target.value)}
            disabled={disabled}
            rows={14}
            placeholder="You are …"
            className="font-mono text-[13px] leading-relaxed"
          />
        </CardContent>
      </Card>
    </div>
  )
}

// ── Model picker ────────────────────────────────────────────────────────────

/**
 * Two-mode model picker:
 *   • "list" — shadcn Select grouped by provider
 *   • "custom" — free-text input (provider:model) for models the registry
 *     doesn't advertise
 *
 * Mode is derived from whether the current value matches a registry entry,
 * with an explicit "Use custom" override the user can flip.
 */
function ModelPicker({
  value,
  onChange,
  options,
  disabled,
  allowEmpty,
  invalid,
}: {
  value: string
  onChange: (v: string) => void
  options: { id: string; provider: string; model: string; vision: boolean }[]
  disabled?: boolean
  allowEmpty?: boolean
  invalid?: boolean
}) {
  const valueIsKnown = !value || options.some((o) => o.id === value)
  const [forceCustom, setForceCustom] = useState(!valueIsKnown && !!value)
  const useCustom = forceCustom || (!valueIsKnown && !!value)

  const grouped = useMemo(() => {
    const g = new Map<string, typeof options>()
    for (const o of options) {
      if (!g.has(o.provider)) g.set(o.provider, [])
      g.get(o.provider)!.push(o)
    }
    return g
  }, [options])

  if (useCustom) {
    return (
      <div className="flex items-center gap-2">
        <Input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="provider:model"
          aria-invalid={invalid || undefined}
          className="flex-1 font-mono"
        />
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setForceCustom(false)
            // If the current value isn't in the registry, clear it so the
            // Select doesn't render an empty placeholder mismatch.
            if (!valueIsKnown) onChange('')
          }}
        >
          Use list
        </Button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <Select
        value={value || undefined}
        onValueChange={(v) => onChange(v ?? '')}
        disabled={disabled}
      >
        <SelectTrigger
          className={cn('flex-1', invalid && 'aria-invalid:border-destructive')}
          aria-invalid={invalid || undefined}
        >
          <SelectValue placeholder={allowEmpty ? '(none)' : 'Select a model…'} />
        </SelectTrigger>
        <SelectContent>
          {[...grouped.entries()].map(([provider, models]) => (
            <SelectGroup key={provider}>
              <SelectLabel>{provider}</SelectLabel>
              {models.map((m) => (
                <SelectItem key={m.id} value={m.id} className="font-mono">
                  {m.model}
                  {m.vision ? ' · vision' : ''}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => setForceCustom(true)}
      >
        Custom
      </Button>
    </div>
  )
}

// ── Field wrapper ───────────────────────────────────────────────────────────

function Field({
  label,
  required,
  className,
  children,
  error,
  hint,
}: {
  label: string
  required?: boolean
  className?: string
  children: React.ReactNode
  /** Zod-sourced error message. When set, rendered in destructive red
   *  under the control; when unset, the hint (if any) is rendered instead. */
  error?: string | null
  /** Helper text shown when there is no error. */
  hint?: string | null
}) {
  // Intentionally a <div>, not a <label>. A <label> wrapper would cause any
  // click inside it to activate the first focusable control in DOM order —
  // in MultiSelect that's the first chip's remove (×) button, which would
  // silently delete a chip when the user clicks empty space in the field.
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <span className="text-xs font-medium text-foreground">
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </span>
      {children}
      {error ? (
        <p className="text-[11px] text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-[11px] text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

// ── Raw → form parser ───────────────────────────────────────────────────────

function parseFormState(raw: string): {
  fm: AgentFrontmatter
  body: string
  error: string | null
} {
  const { fm: fmText, body } = splitFrontmatter(raw)
  const fm: AgentFrontmatter = { name: '', role: 'member' }

  if (!fmText.trim()) {
    return { fm, body, error: 'Missing YAML frontmatter (needs --- … --- header).' }
  }

  try {
    const parsed = parseSimpleYaml(fmText)
    if (typeof parsed.name === 'string') fm.name = parsed.name
    if (parsed.role === 'lead' || parsed.role === 'member') fm.role = parsed.role
    if (typeof parsed.description === 'string') fm.description = parsed.description
    if (typeof parsed.model === 'string') fm.model = parsed.model
    if (typeof parsed.fallback_model === 'string') fm.fallback_model = parsed.fallback_model
    if (typeof parsed.temperature === 'number') fm.temperature = parsed.temperature
    if (typeof parsed.thinking_level === 'string') fm.thinking_level = parsed.thinking_level
    if (Array.isArray(parsed.tools)) fm.tools = parsed.tools.filter((x) => typeof x === 'string')
    if (Array.isArray(parsed.skills)) fm.skills = parsed.skills.filter((x) => typeof x === 'string')
    if (Array.isArray(parsed.mcp)) fm.mcp = parsed.mcp.filter((x) => typeof x === 'string')
    return { fm, body, error: null }
  } catch (err) {
    return { fm, body, error: String((err as Error).message ?? err) }
  }
}

/**
 * Minimal YAML parser — handles the subset our AgentForm emits:
 * scalar key/values and bullet lists of strings. Anything more exotic
 * (nested objects, block scalars, anchors, flow style) is ignored
 * silently; the raw editor remains the escape hatch.
 */
function parseSimpleYaml(text: string): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const lines = text.split(/\r?\n/)
  let currentKey: string | null = null
  let currentList: string[] | null = null

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '')
    if (!line.trim() || line.trim().startsWith('#')) continue

    // List continuation
    const listMatch = /^\s+-\s+(.*)$/.exec(line)
    if (currentList && listMatch) {
      currentList.push(unquote(listMatch[1]))
      continue
    }

    const kvMatch = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line)
    if (!kvMatch) {
      // Unknown indented content — skip gracefully.
      continue
    }
    const [, key, rawValue] = kvMatch
    currentKey = key
    currentList = null

    if (rawValue === '') {
      // Expect list on following lines.
      currentList = []
      out[currentKey] = currentList
      continue
    }
    out[currentKey] = coerce(unquote(rawValue))
  }
  return out
}

function unquote(v: string): string {
  const t = v.trim()
  if (
    (t.startsWith('"') && t.endsWith('"')) ||
    (t.startsWith("'") && t.endsWith("'"))
  ) {
    return t.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\')
  }
  return t
}

function coerce(v: string): unknown {
  if (v === 'true') return true
  if (v === 'false') return false
  if (v === 'null' || v === '~' || v === '') return null
  const n = Number(v)
  if (!Number.isNaN(n) && v.trim() !== '') return n
  return v
}
