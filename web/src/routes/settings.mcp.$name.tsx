import { useNavigate, useParams } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import { AlertCircle, RotateCw } from 'lucide-react'

import { useMcpServerQuery, useRestartMcpServerMutation, useUpdateMcpServerMutation } from '@/queries'
import { useToastStore } from '@/stores/useToastStore'
import { ApiValidationError } from '@/api/client'
import { EditorSubHeader } from '@/components/settings/EditorSubHeader'
import { McpServerForm } from '@/components/settings/McpServerForm'
import {
  draftEquals,
  draftFromServerBody,
  draftToServerBody,
  validateDraft,
  type McpServerDraft,
} from '@/components/settings/McpServerDraft'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * MCP server detail / editor page.
 *
 * Layout mirrors the agent / skill editors:
 *   • sticky `EditorSubHeader` (Save + dirty/invalid status)
 *   • scrollable body capped at `max-w-3xl` with the standard padding
 *
 * The body shows:
 *   1. live status (state, started_at, tools, error) — read-only
 *   2. the editable `McpServerForm` for the saved configuration
 *   3. a Restart action at the bottom (it's a runtime concern, not a save)
 */
export function McpServerDetailPage() {
  const { name } = useParams({ from: '/settings/mcp/$name' })
  const navigate = useNavigate()
  const push = useToastStore((s) => s.push)
  const serverQ = useMcpServerQuery(name)
  const updateMut = useUpdateMcpServerMutation()
  const restartMut = useRestartMcpServerMutation()

  // Seed the editable draft from the saved config payload. We re-seed
  // exactly once per server load (tracking the `name` + version of the
  // config object) so user edits aren't blown away by background refetches.
  const seedDraft = useMemo<McpServerDraft | null>(() => {
    const cfg = serverQ.data?.config
    if (!cfg) return null
    return draftFromServerBody(name, cfg)
  }, [name, serverQ.data?.config])

  const [draft, setDraft] = useState<McpServerDraft | null>(seedDraft)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Adopt the seed once the query lands. Subsequent edits keep `draft`.
  const [seededFor, setSeededFor] = useState<string | null>(null)
  if (seedDraft && seededFor !== name) {
    setSeededFor(name)
    setDraft(seedDraft)
    setSaveError(null)
  }

  const dirty = !!seedDraft && !!draft && !draftEquals(draft, seedDraft)
  const fieldErrors = draft ? validateDraft(draft, { isNew: false }) : null
  const invalid = fieldErrors !== null
  const firstError = fieldErrors ? Object.values(fieldErrors)[0] : null

  const handleSave = async () => {
    if (!draft) return
    setSaveError(null)
    if (invalid) {
      setSaveError(firstError ?? 'Form has validation errors.')
      return
    }
    const result = draftToServerBody(draft)
    if (!result.ok) {
      setSaveError(result.error)
      return
    }
    try {
      await updateMut.mutateAsync({ name, server: result.body })
      push({
        tone: 'success',
        title: `Saved "${name}"`,
        description: 'Available on next turn.',
      })
    } catch (err) {
      const msg = err instanceof ApiValidationError ? err.message : String(err)
      setSaveError(msg)
      push({ tone: 'error', title: 'Save failed', description: msg })
    }
  }

  const handleRestart = async () => {
    try {
      await restartMut.mutateAsync(name)
      push({ tone: 'success', title: `Restarted "${name}"` })
    } catch (err) {
      const msg = err instanceof ApiValidationError ? err.message : String(err)
      push({ tone: 'error', title: `Failed to restart "${name}"`, description: msg })
    }
  }

  const server = serverQ.data

  return (
    <div className="flex h-full flex-col">
      <EditorSubHeader
        kind="mcp"
        name={name}
        path=".openagentd/config/mcp.json"
        dirty={dirty}
        invalid={invalid}
        saving={updateMut.isPending}
        error={saveError}
        validationHint={firstError}
        onSave={handleSave}
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
          {serverQ.isLoading && (
            <p className="text-sm text-muted-foreground">Loading server…</p>
          )}
          {serverQ.isError && (
            <p className="text-sm text-destructive">
              Failed to load: {String(serverQ.error)}
            </p>
          )}

          {server && (
            <>
              <StatusCard server={server} />

              {server.state === 'error' && server.error && (
                <Card size="sm" className="border-destructive/40 bg-destructive/5">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <AlertCircle size={14} className="text-destructive" />
                      Runtime error
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="font-mono text-xs text-destructive">{server.error}</p>
                  </CardContent>
                </Card>
              )}

              {draft ? (
                <McpServerForm
                  value={draft}
                  onChange={setDraft}
                  isNew={false}
                  disabled={updateMut.isPending}
                  errors={fieldErrors}
                />
              ) : (
                <Card size="sm">
                  <CardContent className="pt-4">
                    <p className="text-xs text-muted-foreground">
                      No saved configuration found. The server may have been removed
                      from <span className="font-mono">mcp.json</span>.
                    </p>
                  </CardContent>
                </Card>
              )}

              {dirty && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={() => seedDraft && setDraft(seedDraft)}
                  >
                    Discard changes
                  </Button>
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={() => navigate({ to: '/settings/mcp' })}
                  >
                    Leave without saving
                  </Button>
                </div>
              )}

              <RestartCard
                onRestart={handleRestart}
                pending={restartMut.isPending}
                enabled={server.enabled}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Status card ─────────────────────────────────────────────────────────────

function StatusCard({
  server,
}: {
  server: NonNullable<ReturnType<typeof useMcpServerQuery>['data']>
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Runtime status</CardTitle>
        <CardDescription>Live state of the running connection.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-xs sm:grid-cols-2">
        <Stat label="State">
          <span
            className={
              server.state === 'ready'
                ? 'text-green-600 dark:text-green-500'
                : server.state === 'starting'
                  ? 'text-yellow-600 dark:text-yellow-500'
                  : server.state === 'error'
                    ? 'text-destructive'
                    : 'text-muted-foreground'
            }
          >
            {server.state}
          </span>
        </Stat>
        <Stat label="Transport">
          <span className="font-mono">{server.transport}</span>
        </Stat>
        <Stat label="Enabled">{server.enabled ? 'yes' : 'no'}</Stat>
        <Stat label="Started">
          {server.started_at ? new Date(server.started_at).toLocaleString() : '—'}
        </Stat>

        {server.tool_names.length > 0 && (
          <div className="sm:col-span-2">
            <p className="mb-1.5 text-xs font-medium text-foreground">
              Tools ({server.tool_names.length})
            </p>
            <div className="flex flex-wrap gap-1">
              {server.tool_names.map((tool) => (
                <span
                  key={tool}
                  className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                >
                  {tool}
                </span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{children}</span>
    </div>
  )
}

// ── Restart card ────────────────────────────────────────────────────────────

function RestartCard({
  onRestart,
  pending,
  enabled,
}: {
  onRestart: () => void
  pending: boolean
  enabled: boolean
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Connection</CardTitle>
        <CardDescription>
          Restart the server process without changing its configuration.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button
          variant="outline"
          size="sm"
          onClick={onRestart}
          disabled={pending || !enabled}
          aria-label={pending ? 'Restarting' : 'Restart server'}
        >
          <RotateCw size={12} aria-hidden="true" />
          {pending ? 'Restarting…' : 'Restart'}
        </Button>
        {!enabled && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Server is disabled — enable and save first to restart.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
