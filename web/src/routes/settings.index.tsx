/**
 * /settings — welcome / overview panel shown in the right pane when no
 * category is active. The left rail is always visible; this page just
 * gives the user a friendly summary and quick jumps with live counts.
 */
import { Link } from '@tanstack/react-router'
import {
  ArrowLeft,
  ChevronRight,
  Moon,
  Plug,
  Settings as SettingsIcon,
  Shield,
  Sparkles,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { useIsMobile } from '@/hooks/use-mobile'
import {
  useAgentFilesQuery,
  useMcpServersQuery,
  useSandboxSettingsQuery,
  useSkillFilesQuery,
} from '@/queries'

interface CardProps {
  to: '/settings/agents' | '/settings/skills' | '/settings/mcp' | '/settings/sandbox' | '/settings/dream'
  icon: LucideIcon
  title: string
  description: string
  count: number | null
  countLabel: string
}

function Card({ to, icon: Icon, title, description, count, countLabel }: CardProps) {
  return (
    <Link
      to={to}
      className={cn(
        'group flex items-center gap-4 rounded-xl border border-border bg-card/40 p-4 transition-all',
        'hover:border-border/80 hover:bg-card focus-visible:border-ring focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40',
      )}
    >
      <span
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground ring-1 ring-border transition-colors group-hover:text-foreground"
        aria-hidden="true"
      >
        <Icon size={18} />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold">{title}</span>
          <span className="rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground">
            {count === null ? '–' : count} {countLabel}
          </span>
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{description}</p>
      </div>

      <ChevronRight
        size={16}
        className="shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
        aria-hidden="true"
      />
    </Link>
  )
}

function SectionHeader({ children }: { children: string }) {
  return (
    <h2 className="mb-2 px-1 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
      {children}
    </h2>
  )
}

export function SettingsHubPage() {
  const isMobile = useIsMobile()
  const agentsQ = useAgentFilesQuery()
  const skillsQ = useSkillFilesQuery()
  const mcpQ = useMcpServersQuery()
  const sandboxQ = useSandboxSettingsQuery()

  const agentsCount = agentsQ.data?.agents.length ?? null
  const skillsCount = skillsQ.data?.skills.length ?? null
  const mcpCount = mcpQ.data?.servers.length ?? null
  const sandboxCount = sandboxQ.data?.denied_patterns.length ?? null

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-8 p-4 md:p-8">
        <header className="flex items-center gap-3">
          {/* Mobile: back to cockpit */}
          {isMobile && (
            <Link
              to="/cockpit"
              aria-label="Back to chat"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ArrowLeft size={16} aria-hidden="true" />
            </Link>
          )}
          <span
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-muted-foreground ring-1 ring-border"
            aria-hidden="true"
          >
            <SettingsIcon size={18} />
          </span>
          <div>
            <h1 className="text-lg font-semibold">Settings</h1>
            <p className="text-xs text-muted-foreground">
              Configure your workspace and the agents that run in it.
            </p>
          </div>
        </header>

        <section>
          <SectionHeader>Workspace</SectionHeader>
          <div className="space-y-2">
            <Card
              to="/settings/agents"
              icon={Wrench}
              title="Agents"
              description="Define and edit your agent team — model, tools, system prompt"
              count={agentsCount}
              countLabel={agentsCount === 1 ? 'agent' : 'agents'}
            />
            <Card
              to="/settings/skills"
              icon={Sparkles}
              title="Skills"
              description="Reusable instruction modules agents load on demand"
              count={skillsCount}
              countLabel={skillsCount === 1 ? 'skill' : 'skills'}
            />
            <Card
              to="/settings/mcp"
              icon={Plug}
              title="MCP servers"
              description="External tool providers via Model Context Protocol"
              count={mcpCount}
              countLabel={mcpCount === 1 ? 'server' : 'servers'}
            />
          </div>
        </section>

        <section>
          <SectionHeader>System</SectionHeader>
          <div className="space-y-2">
            <Card
              to="/settings/sandbox"
              icon={Shield}
              title="Sandbox"
              description="Files and folders agents cannot access"
              count={sandboxCount}
              countLabel={sandboxCount === 1 ? 'pattern' : 'patterns'}
            />
            <Card
              to="/settings/dream"
              icon={Moon}
              title="Dream"
              description="Cron agent that synthesises sessions into wiki topics"
              count={null}
              countLabel=""
            />
          </div>
        </section>
      </div>
    </div>
  )
}
