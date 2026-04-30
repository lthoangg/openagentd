/**
 * WikiPanel — file tree + markdown editor for the agent wiki.
 *
 * The wiki lives under ``{OPENAGENTD_WIKI_DIR}``:
 *
 *   system/   — USER.md (single file, always injected into the system prompt)
 *   notes/    — session dumps written by the agent; deletable but not editable
 *   topics/   — dream-synthesised topic knowledge; fully editable
 *
 * The panel lets the user browse the tree, open a file, and save or delete it.
 * Notes are read-only in the editor (agent-written) but can be deleted.
 * The agent also edits these files through filesystem tools during conversation;
 * invalidation is handled by the team store when any write/edit/rm tool_end
 * targets a ``wiki/`` path.
 */

import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Save, Trash2, FileText, Folder, Loader2, ArrowLeft } from 'lucide-react'
import { useIsMobile } from '@/hooks/use-mobile'
import {
  useWikiTreeQuery,
  useWikiFileQuery,
  useWriteWikiFileMutation,
  useDeleteWikiFileMutation,
} from '@/queries'
import { cn } from '@/lib/utils'
import type { WikiFileInfo } from '@/api/types'

interface WikiPanelProps {
  open: boolean
  onClose: () => void
}


type SectionKey = 'system' | 'notes' | 'topics'

type Section = {
  key: SectionKey
  label: string
  hint: string
  files: WikiFileInfo[]
}

export function WikiPanel({ open, onClose }: WikiPanelProps) {
  const isMobile = useIsMobile()
  const { data: tree, isLoading, isError } = useWikiTreeQuery(true)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [mobilePane, setMobilePane] = useState<'tree' | 'editor'>('tree')

  const handleSelect = (path: string) => {
    setSelectedPath(path)
    if (isMobile) setMobilePane('editor')
  }

  const handleBack = () => {
    setMobilePane('tree')
    setSelectedPath(null)
  }

  const sections: Section[] = [
    {
      key: 'system',
      label: 'Wiki',
      hint: 'USER.md (injected every prompt) · INDEX.md (table of contents)',
      files: tree?.system ?? [],
    },
    {
      key: 'notes',
      label: 'Notes',
      hint: 'Unprocessed session notes — pending dream synthesis',
      files: tree?.notes ?? [],
    },
    {
      key: 'topics',
      label: 'Topics',
      hint: 'Dream-synthesised knowledge',
      files: tree?.topics ?? [],
    },
  ]

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/40"
          />

          <motion.div
            initial={{ x: '-100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '-100%', opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
            className="fixed inset-y-0 left-0 z-50 flex w-[min(960px,90vw)] flex-col overflow-hidden bg-(--color-surface) shadow-2xl"
          >
            <header className="flex items-center justify-between border-b border-(--color-border) px-4 py-3">
              <div className="flex items-center gap-2">
                {isMobile && mobilePane === 'editor' && (
                  <button
                    onClick={handleBack}
                    className="rounded p-1 text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text)"
                    aria-label="Back to file list"
                  >
                    <ArrowLeft size={16} />
                  </button>
                )}
                <div>
                  <h2 className="text-sm font-semibold text-(--color-text)">Wiki</h2>
                  <p className="text-xs text-(--color-text-subtle)">
                    Agent knowledge base — synthesised from past conversations
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="rounded p-1 text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text)"
                aria-label="Close wiki panel"
              >
                <X size={16} />
              </button>
            </header>

            {isMobile ? (
              <div className="flex min-h-0 flex-1 flex-col">
                {mobilePane === 'tree' ? (
                  <nav className="flex-1 overflow-y-auto px-2 py-3">
                    <TreeContent
                      isLoading={isLoading}
                      isError={isError}
                      sections={sections}
                      selectedPath={selectedPath}
                      onSelect={handleSelect}
                    />
                  </nav>
                ) : (
                  <div className="min-w-0 flex-1">
                    {selectedPath ? (
                      <WikiEditor
                        key={selectedPath}
                        path={selectedPath}
                        onDeleted={handleBack}
                      />
                    ) : (
                      <EmptyState />
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex min-h-0 flex-1">
                <nav className="w-[220px] shrink-0 overflow-y-auto border-r border-(--color-border) px-2 py-3">
                  <TreeContent
                    isLoading={isLoading}
                    isError={isError}
                    sections={sections}
                    selectedPath={selectedPath}
                    onSelect={handleSelect}
                  />
                </nav>
                <div className="min-w-0 flex-1">
                  {selectedPath ? (
                    <WikiEditor
                      key={selectedPath}
                      path={selectedPath}
                      onDeleted={() => setSelectedPath(null)}
                    />
                  ) : (
                    <EmptyState />
                  )}
                </div>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

// ── Tree helpers ─────────────────────────────────────────────────────────────

function TreeContent({
  isLoading,
  isError,
  sections,
  selectedPath,
  onSelect,
}: {
  isLoading: boolean
  isError: boolean
  sections: Section[]
  selectedPath: string | null
  onSelect: (path: string) => void
}) {
  if (isLoading) {
    return (
      <div className="px-2 py-6 text-center text-xs text-(--color-text-subtle)">
        <Loader2 size={14} className="mx-auto animate-spin" />
      </div>
    )
  }
  if (isError) {
    return <p className="px-2 py-4 text-xs text-(--color-error)">Failed to load wiki</p>
  }
  return (
    <>
      {sections.map((section) => (
        <WikiSection
          key={section.key}
          section={section}
          selectedPath={selectedPath}
          onSelect={onSelect}
        />
      ))}
    </>
  )
}

function WikiSection({
  section,
  selectedPath,
  onSelect,
}: {
  section: Section
  selectedPath: string | null
  onSelect: (path: string) => void
}) {
  return (
    <div className="mb-4">
      <div className="mb-1 flex items-center gap-1.5 px-2 py-1 text-xs font-semibold uppercase tracking-wider text-(--color-text-subtle)">
        <Folder size={12} />
        {section.label}
      </div>
      <p className="mb-1 px-2 text-[10px] text-(--color-text-subtle)">{section.hint}</p>
      {section.files.length === 0 ? (
        <p className="px-2 py-1 text-xs italic text-(--color-text-subtle)">empty</p>
      ) : (
        <ul className="space-y-0.5">
          {section.files.map((file) => {
            const name = file.path.split('/').pop() ?? file.path
            const isActive = file.path === selectedPath
            return (
              <li key={file.path}>
                <button
                  onClick={() => onSelect(file.path)}
                  className={cn(
                    'group flex w-full items-start gap-1.5 rounded px-2 py-1.5 text-left text-xs transition-colors',
                    isActive
                      ? 'bg-(--color-accent-subtle) text-(--color-accent)'
                      : 'text-(--color-text-2) hover:bg-(--color-accent-subtle) hover:text-(--color-text)',
                  )}
                  title={file.description || name}
                >
                  <FileText size={12} className="mt-0.5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{name}</div>
                    {file.description && (
                      <div className="truncate text-[10px] text-(--color-text-subtle)">
                        {file.description}
                      </div>
                    )}
                  </div>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// ── Editor ───────────────────────────────────────────────────────────────────

function WikiEditor({
  path,
  onDeleted,
}: {
  path: string
  onDeleted: () => void
}) {
  const { data: file, isLoading, isError } = useWikiFileQuery(path)
  const writeMutation = useWriteWikiFileMutation()
  const deleteMutation = useDeleteWikiFileMutation()

  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [dirty, setDirty] = useState(false)
  const [charCount, setCharCount] = useState<number>(0)

  // notes/ are read-only (agent-written); everything else (USER.md, INDEX.md, topics/) is editable
  const isReadOnly = path.startsWith('notes/')
  // Root files cannot be deleted — backend enforces this too
  const isDeletable = path !== 'USER.md' && path !== 'INDEX.md'

  const getDraft = (): string => textareaRef.current?.value ?? file?.content ?? ''

  const handleSave = () => {
    if (!dirty || isReadOnly) return
    writeMutation.mutate(
      { path, content: getDraft() },
      { onSuccess: () => setDirty(false) },
    )
  }

  const handleDelete = () => {
    if (!confirm(`Delete wiki file "${path}"? This cannot be undone.`)) return
    deleteMutation.mutate(path, { onSuccess: onDeleted })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isReadOnly && (e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      handleSave()
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-(--color-text-subtle)">
        <Loader2 size={16} className="animate-spin" />
      </div>
    )
  }
  if (isError || !file) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-xs text-(--color-error)">
        Failed to load {path}
      </div>
    )
  }

  const displayChars = charCount || file.content.length

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-(--color-border) px-4 py-2">
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-xs text-(--color-text)">{path}</div>
          {file.description && (
            <div className="truncate text-[10px] text-(--color-text-subtle)">
              {file.description}
            </div>
          )}
        </div>
        <div className="ml-2 flex items-center gap-1">
          {!isReadOnly && (
            <button
              onClick={handleSave}
              disabled={!dirty || writeMutation.isPending}
              className={cn(
                'flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors',
                dirty
                  ? 'text-(--color-success) hover:bg-(--color-success-subtle)'
                  : 'cursor-not-allowed text-(--color-text-subtle)',
              )}
              title="Save (Ctrl+S)"
            >
              {writeMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              Save
            </button>
          )}
          {isDeletable && (
            <button
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium text-(--color-error) transition-colors hover:bg-(--color-error-subtle)"
              title="Delete file"
            >
              <Trash2 size={12} />
              Delete
            </button>
          )}
        </div>
      </div>

      {writeMutation.isError && (
        <div className="border-b border-(--color-border) bg-(--color-error-subtle) px-4 py-2 text-xs text-(--color-error)">
          {(writeMutation.error as Error).message}
        </div>
      )}

      <textarea
        ref={textareaRef}
        defaultValue={file.content}
        readOnly={isReadOnly}
        onInput={(e) => {
          if (isReadOnly) return
          const v = (e.target as HTMLTextAreaElement).value
          setCharCount(v.length)
          if (!dirty) setDirty(true)
        }}
        onKeyDown={handleKeyDown}
        spellCheck={false}
        className={cn(
          'min-h-0 flex-1 resize-none p-4 font-mono text-sm text-(--color-text) focus:outline-none',
          isReadOnly
            ? 'cursor-default bg-(--color-surface-2) text-(--color-text-muted)'
            : 'bg-(--color-bg)',
        )}
        placeholder={
          isReadOnly ? '' :
          path === 'INDEX.md' ? '# Index\n\n- [topic](topics/topic.md) — description\n' :
          'Frontmatter recommended:\n---\ndescription: …\n---\n\n'
        }
      />

      <div className="flex items-center justify-between border-t border-(--color-border) px-4 py-1.5 text-[10px] text-(--color-text-subtle)">
        <span>{displayChars} chars</span>
        {isReadOnly ? (
          <span className="italic">read-only</span>
        ) : dirty ? (
          <span className="text-(--color-accent)">unsaved</span>
        ) : (
          <span>saved</span>
        )}
      </div>
    </div>
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
      <FileText size={24} className="text-(--color-text-subtle)" />
      <p className="text-sm text-(--color-text-2)">Select a file</p>
      <p className="max-w-xs text-xs text-(--color-text-subtle)">
        <span className="font-medium">USER.md</span> is injected into every prompt.{' '}
        <span className="font-medium">INDEX.md</span> is the dream-maintained table of contents.{' '}
        <span className="font-medium">topics/</span> are searched by the agent on demand.{' '}
        <span className="font-medium">notes/</span> shows unprocessed notes — run <code className="font-mono">Dream</code> to synthesise them.
      </p>
    </div>
  )
}
