import { useNavigate, useParams } from '@tanstack/react-router'
import { useState } from 'react'

import { useAgentFileQuery, useUpdateAgentMutation } from '@/queries'
import { useToastStore } from '@/stores/useToastStore'
import { ApiValidationError } from '@/api/client'
import { AgentForm } from '@/components/settings/AgentForm'
import { EditorSubHeader } from '@/components/settings/EditorSubHeader'
import { contentEquals } from '@/components/settings/frontmatter'
import { validateAgentDraft } from '@/components/settings/schema'
import { Button } from '@/components/ui/button'

/**
 * Edit an existing agent. Loads the raw .md, renders the hybrid form,
 * saves via PUT (which auto-reloads the team server-side). On save
 * success the toast shows the reload diff.
 */
export function AgentEditorPage() {
  const { name } = useParams({ from: '/settings/agents/$name' })
  const navigate = useNavigate()
  const push = useToastStore((s) => s.push)
  const { data, isLoading, isError, error, refetch } = useAgentFileQuery(name)
  const updateMut = useUpdateAgentMutation()

  // `draft` is the editor's working copy. Seed it once per `name` with the
  // server content; subsequent saves call `setDraft` explicitly from the
  // mutation response.
  const [draft, setDraft] = useState<string>(() => data?.content ?? '')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [mode, setMode] = useState<'form' | 'raw'>('form')

  // If the query finished *after* mount (common case), adopt its content
  // once. We derive this from state by tracking whether we've ever seeded.
  const [seeded, setSeeded] = useState(!!data?.content)
  if (!seeded && data?.content) {
    setSeeded(true)
    setDraft(data.content)
  }

  // Compare semantically: list-fields (tools, skills) are sets, body
  // trailing whitespace doesn't count. See ``contentEquals`` for rules.
  const dirty = !!data && !contentEquals(draft, data.content)

  // Client-side validation via zod — first error to report. Backend still
  // revalidates on save, but blocking here avoids a round-trip.
  const draftErrors = dirty ? validateAgentDraft(draft) : null
  const invalid = draftErrors !== null
  const firstDraftError = draftErrors ? Object.values(draftErrors)[0] : null

  const handleSave = async () => {
    setSaveError(null)
    if (invalid) {
      setSaveError(firstDraftError ?? 'Form has validation errors.')
      return
    }
    try {
      const res = await updateMut.mutateAsync({ name, content: draft })
      push({
        tone: 'success',
        title: `Saved "${name}"`,
        description: 'Active on next turn.',
      })
      setDraft(res.content)
      refetch()
    } catch (err) {
      const msg = err instanceof ApiValidationError ? err.message : String(err)
      setSaveError(msg)
      push({ tone: 'error', title: 'Save failed', description: msg })
    }
  }

  return (
    <div className="flex h-full flex-col">
      <EditorSubHeader
        kind="agent"
        name={name}
        path={data?.path}
        dirty={dirty}
        invalid={invalid}
        saving={updateMut.isPending}
        error={saveError}
        validationHint={firstDraftError}
        mode={mode}
        onModeChange={setMode}
        onSave={handleSave}
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl p-6">
          {isLoading && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          {isError && (
            <p className="text-sm text-destructive">Failed to load: {String(error)}</p>
          )}
          {data && (
            <AgentForm
              initial={data.content}
              onChange={setDraft}
              disabled={updateMut.isPending}
              isNew={false}
              mode={mode}
              onModeChange={setMode}
            />
          )}
          {dirty && (
            <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
              <Button
                variant="ghost"
                size="xs"
                onClick={() => data && setDraft(data.content)}
              >
                Discard changes
              </Button>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => navigate({ to: '/settings/agents' })}
              >
                Leave without saving
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
