/**
 * McpServerForm — controlled form for an MCP server configuration.
 *
 * Mirrors the AgentForm shape:
 *   - the form is a pure controlled view of `value`; on every edit it
 *     emits a fresh `McpServerDraft` via `onChange`.
 *   - the route owns persistence, dirty/invalid bookkeeping, and the
 *     sticky save bar (rendered separately via `EditorSubHeader`).
 *
 * Draft model + validators live in `./McpServerDraft` so this module
 * stays component-only (Vite fast-refresh requirement).
 */
import { Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import type { KeyValuePair, McpServerDraft } from './McpServerDraft'

interface McpServerFormProps {
  value: McpServerDraft
  onChange: (next: McpServerDraft) => void
  /** When true, the name input is editable. */
  isNew?: boolean
  /** Disable every interactive control (mid-save). */
  disabled?: boolean
  /** Field-level errors keyed by `name | command | url | env | headers`. */
  errors?: Record<string, string> | null
}

export function McpServerForm({
  value,
  onChange,
  isNew,
  disabled,
  errors,
}: McpServerFormProps) {
  const set = (patch: Partial<McpServerDraft>) => onChange({ ...value, ...patch })

  return (
    <div className="flex flex-col gap-4">
      {/* Identity ─────────────────────────────────────────────────── */}
      <Card size="sm">
        <CardHeader>
          <CardTitle>Identity</CardTitle>
          <CardDescription>How agents and the runtime address this server.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field
            label="Name"
            required
            error={errors?.name}
            hint={
              !isNew
                ? 'Persisted key in mcp.json; cannot be renamed.'
                : 'Letters, digits, _ or -; must start with a letter.'
            }
          >
            <Input
              value={value.name}
              onChange={(e) => set({ name: e.target.value })}
              disabled={disabled || !isNew}
              placeholder="filesystem"
              aria-invalid={!!errors?.name || undefined}
              className="font-mono"
            />
          </Field>

          <Field
            label="Status"
            hint={value.enabled ? 'Server is started at runtime.' : 'Server is left stopped.'}
          >
            <EnabledToggle
              value={value.enabled}
              onChange={(enabled) => set({ enabled })}
              disabled={disabled}
            />
          </Field>
        </CardContent>
      </Card>

      {/* Transport ────────────────────────────────────────────────── */}
      <Card size="sm">
        <CardHeader>
          <CardTitle>Transport</CardTitle>
          <CardDescription>How the runtime talks to the server process.</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs
            value={value.transport}
            onValueChange={(v) => set({ transport: v as 'stdio' | 'http' })}
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="stdio" disabled={disabled}>
                Stdio
              </TabsTrigger>
              <TabsTrigger value="http" disabled={disabled}>
                HTTP
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </CardContent>
      </Card>

      {/* Stdio fields ─────────────────────────────────────────────── */}
      {value.transport === 'stdio' && (
        <Card size="sm">
          <CardHeader>
            <CardTitle>Stdio configuration</CardTitle>
            <CardDescription>
              The runtime spawns a subprocess and speaks MCP over stdin/stdout.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Field
              label="Command"
              required
              error={errors?.command}
              hint="Executable to launch (looked up on PATH)."
            >
              <Input
                value={value.command}
                onChange={(e) => set({ command: e.target.value })}
                disabled={disabled}
                placeholder="npx"
                aria-invalid={!!errors?.command || undefined}
                className="font-mono"
              />
            </Field>

            <Field label="Arguments" hint="One per line, in order.">
              <Textarea
                value={value.argsText}
                onChange={(e) => set({ argsText: e.target.value })}
                disabled={disabled}
                rows={4}
                spellCheck={false}
                placeholder="-y&#10;@modelcontextprotocol/server-filesystem&#10;/tmp"
                className="font-mono text-[13px] leading-relaxed"
              />
            </Field>

            <PairListField
              label="Environment variables"
              keyPlaceholder="KEY"
              valuePlaceholder="value"
              error={errors?.env}
              pairs={value.envPairs}
              onChange={(envPairs) => set({ envPairs })}
              disabled={disabled}
            />
          </CardContent>
        </Card>
      )}

      {/* HTTP fields ──────────────────────────────────────────────── */}
      {value.transport === 'http' && (
        <Card size="sm">
          <CardHeader>
            <CardTitle>HTTP configuration</CardTitle>
            <CardDescription>
              The runtime opens a Streamable HTTP session against the URL.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Field
              label="URL"
              required
              error={errors?.url}
              hint="Streamable HTTP endpoint (full URL incl. scheme)."
            >
              <Input
                value={value.url}
                onChange={(e) => set({ url: e.target.value })}
                disabled={disabled}
                placeholder="https://mcp.example.com/v1"
                aria-invalid={!!errors?.url || undefined}
                className="font-mono"
              />
            </Field>

            <PairListField
              label="Headers"
              keyPlaceholder="Header-Name"
              valuePlaceholder="value"
              error={errors?.headers}
              pairs={value.headerPairs}
              onChange={(headerPairs) => set({ headerPairs })}
              disabled={disabled}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Field wrapper (mirrors AgentForm.Field) ─────────────────────────────────

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
  error?: string | null
  hint?: string | null
}) {
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

// ── Enabled toggle ──────────────────────────────────────────────────────────

/**
 * Two-button segmented toggle. We don't have a shadcn Switch in the
 * codebase, and a styled native checkbox feels out of place next to the
 * Tabs/Card aesthetic — the segmented control matches it.
 */
function EnabledToggle({
  value,
  onChange,
  disabled,
}: {
  value: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Server enabled state"
      className="inline-flex h-9 rounded-md bg-muted p-0.5 ring-1 ring-border"
    >
      <ToggleOption
        active={value}
        onClick={() => onChange(true)}
        disabled={disabled}
        label="Enabled"
      />
      <ToggleOption
        active={!value}
        onClick={() => onChange(false)}
        disabled={disabled}
        label="Disabled"
      />
    </div>
  )
}

function ToggleOption({
  active,
  onClick,
  disabled,
  label,
}: {
  active: boolean
  onClick: () => void
  disabled?: boolean
  label: string
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex-1 rounded-sm px-3 text-xs font-medium transition-colors',
        active
          ? 'bg-background text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      {label}
    </button>
  )
}

// ── Pair list field (env vars, headers) ─────────────────────────────────────

function PairListField({
  label,
  keyPlaceholder,
  valuePlaceholder,
  error,
  pairs,
  onChange,
  disabled,
}: {
  label: string
  keyPlaceholder: string
  valuePlaceholder: string
  error?: string | null
  pairs: KeyValuePair[]
  onChange: (next: KeyValuePair[]) => void
  disabled?: boolean
}) {
  const setAt = (idx: number, patch: Partial<KeyValuePair>) =>
    onChange(pairs.map((p, i) => (i === idx ? { ...p, ...patch } : p)))
  const removeAt = (idx: number) => onChange(pairs.filter((_, i) => i !== idx))
  const append = () => onChange([...pairs, { key: '', value: '' }])

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">{label}</span>
        <Button
          size="xs"
          variant="ghost"
          onClick={append}
          disabled={disabled}
          aria-label={`Add ${label.toLowerCase()}`}
        >
          <Plus size={11} aria-hidden="true" />
          Add
        </Button>
      </div>

      {pairs.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">None.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {pairs.map((pair, idx) => (
            <div key={idx} className="flex items-center gap-1.5">
              <Input
                value={pair.key}
                onChange={(e) => setAt(idx, { key: e.target.value })}
                disabled={disabled}
                placeholder={keyPlaceholder}
                className="flex-1 font-mono text-xs"
              />
              <Input
                value={pair.value}
                onChange={(e) => setAt(idx, { value: e.target.value })}
                disabled={disabled}
                placeholder={valuePlaceholder}
                className="flex-1 font-mono text-xs"
              />
              <Button
                size="icon-xs"
                variant="ghost"
                onClick={() => removeAt(idx)}
                disabled={disabled}
                aria-label={`Remove ${pair.key || 'entry'}`}
              >
                <Trash2 size={12} />
              </Button>
            </div>
          ))}
        </div>
      )}

      {error && <p className="text-[11px] text-destructive">{error}</p>}
    </div>
  )
}
