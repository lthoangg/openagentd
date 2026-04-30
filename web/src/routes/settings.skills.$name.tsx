import { useNavigate, useParams } from '@tanstack/react-router'
import { useState } from 'react'

import { useSkillFileQuery, useUpdateSkillMutation } from '@/queries'
import { useToastStore } from '@/stores/useToastStore'
import { ApiValidationError } from '@/api/client'
import { EditorSubHeader } from '@/components/settings/EditorSubHeader'
import { contentEquals } from '@/components/settings/frontmatter'
import { validateSkillDraft } from '@/components/settings/schema'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'

/**
 * Skill editor — lighter than the agent editor because skills have an
 * open-ended schema (only ``name`` + ``description`` are required).
 * We render a single raw .md textarea and let the user go wild.
 */
export function SkillEditorPage() {
  const { name } = useParams({ from: '/settings/skills/$name' })
  const navigate = useNavigate()
  const push = useToastStore((s) => s.push)
  const { data, isLoading, isError, error, refetch } = useSkillFileQuery(name)
  const updateMut = useUpdateSkillMutation()
  const [draft, setDraft] = useState<string>(() => data?.content ?? '')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [seeded, setSeeded] = useState(!!data?.content)
  if (!seeded && data?.content) {
    setSeeded(true)
    setDraft(data.content)
  }

  const dirty = !!data && !contentEquals(draft, data.content)
  const draftErrors = dirty ? validateSkillDraft(draft) : null
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
        kind="skill"
        name={name}
        path={data?.path}
        dirty={dirty}
        invalid={invalid}
        saving={updateMut.isPending}
        error={saveError}
        validationHint={firstDraftError}
        onSave={handleSave}
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl p-6">
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="text-sm text-destructive">Failed to load: {String(error)}</p>
          )}
          {data && (
            <Card size="sm">
              <CardHeader>
                <CardTitle>Skill source</CardTitle>
                <CardDescription>
                  Frontmatter (<span className="font-mono">name</span>,{' '}
                  <span className="font-mono">description</span>) is required;
                  the body is the instruction the agent loads on demand.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  disabled={updateMut.isPending}
                  rows={28}
                  spellCheck={false}
                  aria-invalid={invalid || undefined}
                  className="font-mono text-[13px] leading-relaxed"
                />
              </CardContent>
            </Card>
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
                onClick={() => navigate({ to: '/settings/skills' })}
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
