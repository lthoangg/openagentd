/**
 * CategoryList — middle column of the three-column settings layout.
 *
 *   ┌─────────────────────┐
 *   │  Agents      [+]    │
 *   │  ┌───────────────┐  │
 *   │  │ search        │  │
 *   │  └───────────────┘  │
 *   │  • Coder            │  ← compact rows; selected row highlighted
 *   │  • Reviewer         │
 *   └─────────────────────┘
 *
 * Each list category (`agents`, `skills`, `mcp`) is implemented as its
 * own small component so it only mounts the query it actually needs.
 * The shared chrome (header / search / body container) lives in
 * `<ListShell />` and is given pre-shaped rows.
 *
 * Sandbox is a singleton (no list); the parent layout decides whether
 * to mount this component at all.
 */
import { Link, useParams } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  Crown,
  Plug,
  Plus,
  Search,
  Sparkles,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useIsMobile } from '@/hooks/use-mobile'

import { type ServerStatus } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import {
  useAgentFilesQuery,
  useMcpServersQuery,
  useSkillFilesQuery,
} from '@/queries'

// ─── Types ─────────────────────────────────────────────────────────────────

type Kind = 'agents' | 'skills' | 'mcp'

interface ListRow {
  name: string
  subtitle: string
  icon: LucideIcon
  iconTone: 'muted' | 'accent'
  invalid?: boolean
  invalidReason?: string
  /** Only set on MCP rows; rendered as a status dot in the trailing slot. */
  mcpStatus?: ServerStatus
}

type DetailRoute =
  | '/settings/agents/$name'
  | '/settings/skills/$name'
  | '/settings/mcp/$name'

type NewRoute =
  | '/settings/agents/new'
  | '/settings/skills/new'
  | '/settings/mcp/new'

interface KindMeta {
  title: string
  placeholder: string
  detailRoute: DetailRoute
  newRoute: NewRoute
  newLabel: string
  emptyTitle: string
  emptyBody: string
}

const META: Record<Kind, KindMeta> = {
  agents: {
    title: 'Agents',
    placeholder: 'Search agents…',
    detailRoute: '/settings/agents/$name',
    newRoute: '/settings/agents/new',
    newLabel: 'New agent',
    emptyTitle: 'No agents yet',
    emptyBody: 'Define a team member with a model, tools, and a system prompt.',
  },
  skills: {
    title: 'Skills',
    placeholder: 'Search skills…',
    detailRoute: '/settings/skills/$name',
    newRoute: '/settings/skills/new',
    newLabel: 'New skill',
    emptyTitle: 'No skills yet',
    emptyBody: 'Reusable instruction modules agents load on demand.',
  },
  mcp: {
    title: 'MCP servers',
    placeholder: 'Search servers…',
    detailRoute: '/settings/mcp/$name',
    newRoute: '/settings/mcp/new',
    newLabel: 'New server',
    emptyTitle: 'No MCP servers yet',
    emptyBody: 'External tool providers via Model Context Protocol.',
  },
}

const STATE_COLOR: Record<ServerStatus['state'], string> = {
  ready: 'bg-green-500',
  starting: 'bg-yellow-500',
  error: 'bg-destructive',
  stopped: 'bg-muted-foreground/40',
}

// ─── Public entry point ────────────────────────────────────────────────────

interface CategoryListProps {
  kind: Kind
}

/**
 * Switch on `kind` to mount one of three small per-kind containers. Each
 * container only calls its own query, so navigating between categories
 * doesn't keep all three in flight.
 */
export function CategoryList({ kind }: CategoryListProps) {
  switch (kind) {
    case 'agents':
      return <AgentsList />
    case 'skills':
      return <SkillsList />
    case 'mcp':
      return <McpList />
  }
}

// ─── Per-kind containers ───────────────────────────────────────────────────

function AgentsList() {
  const { data, isLoading, isError } = useAgentFilesQuery()
  const rows = useMemo<ListRow[]>(
    () =>
      data?.agents.map((a) => ({
        name: a.name,
        subtitle: a.description || a.model || 'No description',
        icon: a.role === 'lead' ? Crown : Wrench,
        iconTone: a.role === 'lead' ? 'accent' : 'muted',
        invalid: !a.valid,
        invalidReason: a.error ?? undefined,
      })) ?? [],
    [data?.agents],
  )
  return <ListShell meta={META.agents} rows={rows} isLoading={isLoading} isError={isError} />
}

function SkillsList() {
  const { data, isLoading, isError } = useSkillFilesQuery()
  const rows = useMemo<ListRow[]>(
    () =>
      data?.skills.map((s) => ({
        name: s.name,
        subtitle: s.description || 'No description',
        icon: Sparkles,
        iconTone: 'muted',
        invalid: !s.valid,
        invalidReason: s.error ?? undefined,
      })) ?? [],
    [data?.skills],
  )
  return <ListShell meta={META.skills} rows={rows} isLoading={isLoading} isError={isError} />
}

function McpList() {
  const { data, isLoading, isError } = useMcpServersQuery()
  const rows = useMemo<ListRow[]>(
    () =>
      data?.servers.map((srv) => ({
        name: srv.name,
        subtitle: `${srv.transport}${!srv.enabled ? ' · disabled' : ''}`,
        icon: Plug,
        iconTone: 'muted',
        mcpStatus: srv,
      })) ?? [],
    [data?.servers],
  )
  return <ListShell meta={META.mcp} rows={rows} isLoading={isLoading} isError={isError} />
}

// ─── Shared chrome ─────────────────────────────────────────────────────────

interface ListShellProps {
  meta: KindMeta
  rows: ListRow[]
  isLoading: boolean
  isError: boolean
}

function ListShell({ meta, rows, isLoading, isError }: ListShellProps) {
  const isMobile = useIsMobile()
  // `useParams({ strict: false })` returns the matched `$name` (or undefined)
  // for any active detail route. No need to parse the pathname manually.
  const { name: selected } = useParams({ strict: false }) as { name?: string }

  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const t = query.trim().toLowerCase()
    if (!t) return rows
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(t) ||
        r.subtitle.toLowerCase().includes(t),
    )
  }, [rows, query])

  return (
    <aside
      aria-label={meta.title}
      className={
        isMobile
          ? 'flex h-full min-h-0 flex-1 flex-col border-r-0 bg-background'
          : 'flex h-full w-72 shrink-0 flex-col border-r border-border bg-background'
      }
    >
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-3">
        {/* Mobile: back arrow to return to settings hub */}
        {isMobile && (
          <Link
            to="/settings"
            aria-label="Back to settings"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ArrowLeft size={16} aria-hidden="true" />
          </Link>
        )}
        <h2 className="flex-1 truncate text-sm font-semibold">{meta.title}</h2>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label={meta.newLabel}
                render={<Link to={meta.newRoute} />}
              >
                <Plus size={14} />
              </Button>
            }
          />
          <TooltipContent>{meta.newLabel}</TooltipContent>
        </Tooltip>
      </header>

      {/* Search */}
      {rows.length > 0 && (
        <div className="border-b border-border p-2">
          <div className="relative">
            <Search
              size={12}
              className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={meta.placeholder}
              aria-label={meta.placeholder}
              className="h-8 pl-7 text-sm"
            />
          </div>
        </div>
      )}

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading && (
          <p className="px-3 py-6 text-center text-xs text-muted-foreground">
            Loading…
          </p>
        )}
        {isError && (
          <p className="px-3 py-6 text-center text-xs text-destructive">
            Failed to load.
          </p>
        )}
        {!isLoading && !isError && rows.length === 0 && (
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            <p className="text-sm font-medium">{meta.emptyTitle}</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {meta.emptyBody}
            </p>
            <Button size="sm" render={<Link to={meta.newRoute} />}>
              <Plus size={12} aria-hidden="true" />
              {meta.newLabel}
            </Button>
          </div>
        )}
        {!isLoading && !isError && rows.length > 0 && filtered.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-muted-foreground">
            No matches for &ldquo;{query}&rdquo;.
          </p>
        )}
        {!isLoading && !isError && filtered.length > 0 && (
          <ul className="px-1 py-1.5">
            {filtered.map((row) => (
              <li key={row.name}>
                <ListRowLink
                  row={row}
                  detailRoute={meta.detailRoute}
                  active={selected === row.name}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}

// ─── Row + status dot ──────────────────────────────────────────────────────

function ListRowLink({
  row,
  detailRoute,
  active,
}: {
  row: ListRow
  detailRoute: DetailRoute
  active: boolean
}) {
  const Icon = row.icon
  return (
    <Link
      to={detailRoute}
      params={{ name: row.name }}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors',
        'hover:bg-muted',
        'focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40',
        active && 'bg-muted',
      )}
    >
      <span
        className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center rounded-md ring-1',
          row.iconTone === 'accent'
            ? 'bg-foreground/5 text-foreground ring-border'
            : 'bg-muted text-muted-foreground ring-border',
        )}
        aria-hidden="true"
      >
        <Icon size={13} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              'truncate text-sm',
              active ? 'font-semibold text-foreground' : 'font-medium',
            )}
          >
            {row.name}
          </span>
          {row.invalid && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <span className="text-destructive">
                    <AlertCircle size={11} aria-label="Invalid configuration" />
                  </span>
                }
              />
              <TooltipContent>
                {row.invalidReason ?? 'Invalid configuration'}
              </TooltipContent>
            </Tooltip>
          )}
        </div>
        {row.subtitle && (
          <p className="truncate text-[11px] text-muted-foreground">
            {row.subtitle}
          </p>
        )}
      </div>
      {row.mcpStatus && <McpStatusDot server={row.mcpStatus} />}
    </Link>
  )
}

function McpStatusDot({ server }: { server: ServerStatus }) {
  if (server.state === 'error') {
    return (
      <span
        className="flex shrink-0 items-center text-destructive"
        title={server.error ?? 'Server failed to start'}
        aria-label={`Error: ${server.error ?? 'unknown'}`}
      >
        <AlertCircle size={12} />
      </span>
    )
  }
  return (
    <span
      className={cn('h-2 w-2 shrink-0 rounded-full', STATE_COLOR[server.state])}
      title={server.state}
      aria-label={`State: ${server.state}`}
    />
  )
}
