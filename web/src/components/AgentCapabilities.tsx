/**
 * AgentCapabilities — right-side drawer showing per-agent details.
 *
 * Shape: slide-in drawer from the right (mirror of MemoryPanel).
 * When 2+ agents are available, a switcher row at the top lets the user
 * pick one; the body shows a single agent at a time. When there is only
 * one agent, the switcher is hidden.
 *
 * Visual language:
 *   - No avatars/robot icons. Each agent identified by status dot + name.
 *   - Role shown as a pill next to the name.
 *   - Only enabled multimodal capabilities render (no dimmed noise).
 *   - Tools collapsible; search input appears above the list when >8 tools.
 */

import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  Wrench,
  ChevronDown,
  Search,
  ImageIcon,
  FileText,
  Mic,
  Video,
  ArrowRight,
  Sparkles,
  Plug,
} from 'lucide-react'
import { useTeamAgentsQuery } from '@/queries/useAgentsQuery'
import type { AgentInfo, AgentCapabilities as AgentCapabilitiesType } from '@/api/types'
import type { AgentStream } from '@/stores/useTeamStore'

// ── Status dot ────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status?: string }) {
  const cls =
    status === 'working'
      ? 'bg-(--color-accent) shadow-[0_0_5px_var(--color-accent)] animate-pulse'
      : status === 'error'
        ? 'bg-(--color-error)'
        : 'bg-(--color-success)'
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${cls}`} aria-hidden />
}

// ── Role pill ─────────────────────────────────────────────────────────────────

function RolePill({ isLead }: { isLead: boolean }) {
  return (
    <span
      className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
        isLead
          ? 'bg-(--color-accent-subtle) text-(--color-accent)'
          : 'bg-(--color-accent-dim) text-(--color-text-muted)'
      }`}
    >
      {isLead ? 'Lead' : 'Member'}
    </span>
  )
}

// ── Capability chips (enabled only) ──────────────────────────────────────────

interface CapabilityChip {
  key: string
  label: string
  icon: React.ComponentType<{ size?: number; className?: string }>
}

function CapabilityChips({ chips }: { chips: CapabilityChip[] }) {
  if (chips.length === 0) {
    return <span className="text-xs italic text-(--color-text-muted)">—</span>
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {chips.map(({ key, label, icon: Icon }) => (
        <span
          key={key}
          className="flex items-center gap-1 rounded-md bg-(--color-accent-subtle) px-2 py-0.5 text-xs text-(--color-text-2) ring-1 ring-(--color-border-strong)"
          title={label}
        >
          <Icon size={11} className="text-(--color-text-muted)" />
          {label}
        </span>
      ))}
    </div>
  )
}

function Capabilities({
  caps,
  tools,
}: {
  caps: AgentCapabilitiesType
  tools: AgentInfo['tools']
}) {
  // Tools can grant output capabilities beyond the model's native ones.
  // e.g. a text-only model + `generate_image` tool → still produces images;
  // `generate_video` (Veo) likewise adds a video output channel even when
  // the underlying chat model has no native video output.
  const canGenerateImage = caps.output.image || tools.some((t) => t.name === 'generate_image')
  const canGenerateVideo = tools.some((t) => t.name === 'generate_video')

  const inputChips: CapabilityChip[] = [
    caps.input.vision && { key: 'vision', label: 'Vision', icon: ImageIcon },
    caps.input.document_text && { key: 'docs', label: 'Documents', icon: FileText },
    caps.input.audio && { key: 'audio-in', label: 'Audio', icon: Mic },
    caps.input.video && { key: 'video', label: 'Video', icon: Video },
  ].filter(Boolean) as CapabilityChip[]

  const outputChips: CapabilityChip[] = [
    caps.output.text && { key: 'text-out', label: 'Text', icon: FileText },
    canGenerateImage && { key: 'image-out', label: 'Image', icon: ImageIcon },
    canGenerateVideo && { key: 'video-out', label: 'Video', icon: Video },
    caps.output.audio && { key: 'audio-out', label: 'Audio', icon: Mic },
  ].filter(Boolean) as CapabilityChip[]

  // Nothing to say — skip the whole section.
  if (inputChips.length === 0 && outputChips.length === 0) return null

  return (
    <section className="border-t border-(--color-border) px-5 py-4">
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-(--color-text-muted)">
        Capabilities
      </h3>
      <div className="flex flex-wrap items-center gap-2">
        <CapabilityChips chips={inputChips} />
        {inputChips.length > 0 && outputChips.length > 0 && (
          <ArrowRight size={12} className="text-(--color-text-subtle)" aria-hidden />
        )}
        <CapabilityChips chips={outputChips} />
      </div>
    </section>
  )
}

// ── Tool row ──────────────────────────────────────────────────────────────────

function ToolRow({ name, description }: { name: string; description: string }) {
  const [open, setOpen] = useState(false)
  const hasDesc = description.trim().length > 0
  return (
    <div className="overflow-hidden rounded-lg border border-(--color-border) bg-(--color-bg) transition-colors hover:border-(--color-border-strong)">
      <button
        onClick={() => hasDesc && setOpen((v) => !v)}
        className={`flex w-full items-center gap-2.5 px-3 py-2 text-left ${hasDesc ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <Wrench size={12} className="shrink-0 text-(--color-text-muted)" />
        <code className="flex-1 truncate font-mono text-xs font-medium text-(--color-text)">{name}</code>
        {hasDesc && (
          <ChevronDown
            size={12}
            className={`shrink-0 text-(--color-text-muted) transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
          />
        )}
      </button>
      <AnimatePresence initial={false}>
        {open && hasDesc && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="overflow-hidden"
          >
            <p className="border-t border-(--color-border) px-3 py-2 text-xs leading-relaxed text-(--color-text-muted)">
              {description}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Tools section ─────────────────────────────────────────────────────────────

const TOOL_SEARCH_THRESHOLD = 8

interface ToolGroup {
  /** Group identifier — null for built-ins, server name otherwise. */
  server: string | null
  tools: AgentInfo['tools']
}

/** Group tools by origin. Membership is derived from the `mcp_<server>_<tool>`
 *  naming convention enforced by `MCPTool.__init__` on the backend — the same
 *  convention the permission system already relies on, so it's the public
 *  contract. Servers listed in `mcp_servers` always appear, even with zero
 *  tools (configured but not ready); silently hiding them is worse than
 *  surfacing the state. */
function groupTools(
  tools: AgentInfo['tools'],
  mcpServers: string[],
): ToolGroup[] {
  // Sort servers longest-prefix-first so a hypothetical `mcp_foo_bar_*` server
  // is matched before `mcp_foo_*` would steal its tools.
  const servers = [...mcpServers].sort((a, b) => b.length - a.length)
  const buckets = new Map<string, AgentInfo['tools']>(
    mcpServers.map((s) => [s, []]),
  )
  const builtins: AgentInfo['tools'] = []

  for (const tool of tools) {
    const owner = servers.find((s) => tool.name.startsWith(`mcp_${s}_`))
    if (owner) buckets.get(owner)!.push(tool)
    else builtins.push(tool)
  }

  const groups: ToolGroup[] = []
  if (builtins.length > 0) groups.push({ server: null, tools: builtins })
  for (const name of [...mcpServers].sort()) {
    groups.push({ server: name, tools: buckets.get(name) ?? [] })
  }
  return groups
}

function ToolGroupHeader({
  server,
  count,
}: {
  server: string | null
  count: number
}) {
  if (server === null) {
    return (
      <div className="flex items-center gap-2 px-5 pt-3 pb-1.5">
        <h4 className="text-[10px] font-semibold uppercase tracking-widest text-(--color-text-muted)">
          Built-in
        </h4>
        <span className="rounded-full bg-(--color-accent-dim) px-2 py-0.5 text-[10px] text-(--color-text-muted)">
          {count}
        </span>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2 px-5 pt-3 pb-1.5">
      <Plug size={11} className="text-(--color-text-muted)" aria-hidden />
      <h4 className="text-[10px] font-semibold uppercase tracking-widest text-(--color-text-muted)">
        MCP · {server}
      </h4>
      <span className="rounded-full bg-(--color-accent-dim) px-2 py-0.5 text-[10px] text-(--color-text-muted)">
        {count}
      </span>
    </div>
  )
}

function Tools({
  tools,
  mcpServers,
}: {
  tools: AgentInfo['tools']
  mcpServers: string[]
}) {
  const [query, setQuery] = useState('')
  const showSearch = tools.length > TOOL_SEARCH_THRESHOLD

  const filteredTools = useMemo(() => {
    if (!query.trim()) return tools
    const q = query.toLowerCase()
    return tools.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q),
    )
  }, [tools, query])

  // Always pass the full mcpServers list so the user can see configured-but-empty
  // servers; once they type a query, we hide empty groups so the filtered view
  // doesn't get padded out by sections that match nothing.
  const groups = useMemo(() => {
    const all = groupTools(filteredTools, mcpServers)
    if (!query.trim()) return all
    return all.filter((g) => g.tools.length > 0)
  }, [filteredTools, mcpServers, query])

  if (tools.length === 0 && mcpServers.length === 0) return null

  return (
    <section className="flex min-h-0 flex-1 flex-col border-t border-(--color-border)">
      <div className="flex shrink-0 items-center gap-2 px-5 pt-4 pb-2">
        <h3 className="text-[10px] font-semibold uppercase tracking-widest text-(--color-text-muted)">
          Tools
        </h3>
        <span className="rounded-full bg-(--color-accent-dim) px-2 py-0.5 text-[10px] text-(--color-text-muted)">
          {tools.length}
        </span>
      </div>

      {showSearch && (
        <div className="shrink-0 px-5 pb-2">
          <div className="flex items-center gap-2 rounded-lg border border-(--color-border) bg-(--color-bg) px-2.5 py-1.5 focus-within:border-(--color-border-strong)">
            <Search size={12} className="shrink-0 text-(--color-text-muted)" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter tools…"
              className="min-w-0 flex-1 bg-transparent text-xs text-(--color-text) placeholder:text-(--color-text-subtle) focus:outline-none"
              aria-label="Filter tools"
            />
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto pb-5">
        {filteredTools.length === 0 && query.trim() ? (
          <p className="px-5 pt-2 text-xs italic text-(--color-text-muted)">
            No tools match “{query}”.
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.server ?? '__builtin__'}>
              <ToolGroupHeader server={group.server} count={group.tools.length} />
              <div className="space-y-1.5 px-5">
                {group.tools.length === 0 ? (
                  <p className="text-xs italic text-(--color-text-muted)">
                    Server not ready — no tools available.
                  </p>
                ) : (
                  group.tools.map((t) => (
                    <ToolRow key={t.name} name={t.name} description={t.description} />
                  ))
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  )
}

// ── Skills section ────────────────────────────────────────────────────────────

function Skills({ skills }: { skills: AgentInfo['skills'] }) {
  return (
    <section className="border-t border-(--color-border) px-5 py-4">
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-(--color-text-muted)">
        Skills
      </h3>
      {skills.length === 0 ? (
        <p className="text-xs italic text-(--color-text-muted)">None configured.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {skills.map((s) => (
            <span
              key={s.name}
              title={s.description || undefined}
              className="flex cursor-default items-center gap-1 rounded-md bg-(--color-accent-subtle) px-2 py-0.5 font-mono text-xs text-(--color-text-2) ring-1 ring-(--color-border-strong)"
            >
              <Sparkles size={10} className="text-(--color-text-muted)" />
              {s.name}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

// ── Switcher ──────────────────────────────────────────────────────────────────

function AgentSwitcher({
  agents,
  selectedName,
  leadName,
  streams,
  onSelect,
}: {
  agents: AgentInfo[]
  selectedName: string
  leadName: string | null
  streams: Record<string, AgentStream>
  onSelect: (name: string) => void
}) {
  return (
    <div className="shrink-0 border-b border-(--color-border) bg-(--color-surface-2) px-3 py-2">
      <div className="flex flex-wrap items-center gap-1">
        {agents.map((agent) => {
          const active = agent.name === selectedName
          const isLead = leadName ? agent.name === leadName : false
          const stream = streams[agent.name]
          return (
            <button
              key={agent.name}
              onClick={() => onSelect(agent.name)}
              className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                active
                  ? 'bg-(--color-accent-subtle) text-(--color-text) ring-1 ring-(--color-border-strong)'
                  : 'text-(--color-text-muted) hover:bg-(--color-accent-dim) hover:text-(--color-text-2)'
              }`}
              aria-pressed={active}
            >
              <StatusDot status={stream?.status} />
              <span className={`font-medium ${isLead ? 'text-(--color-accent)' : ''}`}>
                {agent.name}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

interface AgentCapabilitiesProps {
  /** Controls drawer visibility. Parent keeps the component mounted so
   *  framer-motion can play both the enter and exit animations. */
  open: boolean
  /** For team mode: ordered agent names (lead first). Empty = single-agent. */
  agentNames?: string[]
  agentStreams?: Record<string, AgentStream>
  onClose: () => void
}

export function AgentCapabilities({
  open,
  agentNames = [],
  agentStreams = {},
  onClose,
}: AgentCapabilitiesProps) {
  const { data, isLoading, refetch } = useTeamAgentsQuery()

  // Refresh on open
  useEffect(() => {
    if (open) refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Close on Escape (only while open)
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])

  const allAgents: AgentInfo[] = data?.agents ?? []
  const byName = new Map(allAgents.map((a) => [a.name, a]))

  // Resolve which agents to show. Prefer the caller's ordering; fall back to
  // the API list so the panel is never blank.
  const display: AgentInfo[] = (() => {
    if (agentNames.length === 0) return allAgents
    const ordered = agentNames.map((n) => byName.get(n)).filter(Boolean) as AgentInfo[]
    return ordered.length > 0 ? ordered : allAgents
  })()

  // Lead comes from the API `is_lead` flag if present, else first in list.
  const leadFromApi = allAgents.find(
    (a) => (a as AgentInfo & { is_lead?: boolean }).is_lead,
  )
  const leadName = display.length > 1 ? (leadFromApi?.name ?? display[0]?.name ?? null) : null

  const [selectedName, setSelectedName] = useState<string | null>(null)

  // Keep the selection in sync with the available agents. Default to the
  // first agent (lead when present).
  useEffect(() => {
    if (display.length === 0) {
      setSelectedName(null)
      return
    }
    if (!selectedName || !display.some((a) => a.name === selectedName)) {
      setSelectedName(display[0].name)
    }
  }, [display, selectedName])

  const selected = selectedName ? byName.get(selectedName) ?? display[0] : display[0]

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/40"
          />

          <motion.aside
            key="drawer"
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
            className="fixed inset-y-0 right-0 z-50 flex w-[min(560px,90vw)] flex-col overflow-hidden border-l border-(--color-border) bg-(--color-surface) shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-label="Agent details"
          >
        {/* Header */}
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-(--color-border) px-5 py-4">
          {isLoading || !selected ? (
            <div className="h-6 w-48 animate-pulse rounded bg-(--color-accent-dim)" />
          ) : (
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <StatusDot status={agentStreams[selected.name]?.status} />
                <h2 className="truncate text-base font-semibold text-(--color-text)">
                  {selected.name}
                </h2>
                <RolePill isLead={leadName === selected.name} />
              </div>
              {selected.model && (
                <p className="mt-1 truncate font-mono text-xs text-(--color-text-muted)">
                  {selected.model}
                </p>
              )}
            </div>
          )}
          <button
            onClick={onClose}
            className="shrink-0 rounded-md p-1.5 text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text-2)"
            aria-label="Close (Esc)"
            title="Close (Esc)"
          >
            <X size={16} />
          </button>
        </header>

        {/* Agent switcher — only when 2+ agents */}
        {display.length > 1 && selected && (
          <AgentSwitcher
            agents={display}
            selectedName={selected.name}
            leadName={leadName}
            streams={agentStreams}
            onSelect={setSelectedName}
          />
        )}

        {/* Body */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {isLoading || !selected ? (
            <div className="flex-1 space-y-3 p-5">
              <div className="h-16 animate-pulse rounded-xl bg-(--color-accent-dim)" />
              <div className="h-24 animate-pulse rounded-xl bg-(--color-accent-dim)" />
              <div className="h-40 animate-pulse rounded-xl bg-(--color-accent-dim)" />
            </div>
          ) : (
            <>
              {/* Description */}
              <section className="shrink-0 px-5 py-4">
                <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-(--color-text-muted)">
                  About
                </h3>
                <p className="text-sm leading-relaxed text-(--color-text-2)">
                  {selected.description?.trim() || (
                    <span className="italic text-(--color-text-muted)">No description.</span>
                  )}
                </p>
              </section>

              <Skills skills={selected.skills} />

              {selected.capabilities && (
                <Capabilities caps={selected.capabilities} tools={selected.tools} />
              )}

              <Tools tools={selected.tools} mcpServers={selected.mcp_servers ?? []} />
            </>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-(--color-border) px-5 py-2.5">
          <p className="text-[11px] text-(--color-text-muted)">
            Esc or click outside to close · Ctrl+A to toggle
          </p>
        </div>
      </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
