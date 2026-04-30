/**
 * useTeamCommands — assembles the Command Palette command list for
 * the team chat view.
 *
 * The palette commands are pure data, but they close over a lot of
 * parent-owned state and callbacks (current view mode, open/focused
 * agents, navigate, the various toggle/cycle handlers). Wrapping the
 * assembly in a hook keeps the parent's render body focused on layout
 * while still threading the closures naturally.
 *
 * Group conventions used by ``CommandPalette``:
 *   - ``Team``       — session lifecycle (new chat, …)
 *   - ``View``       — view-mode + panel toggles
 *   - ``Agents``     — per-agent navigation + cycling
 *   - ``Navigation`` — top-level routes
 *   - ``Settings``   — agent / skill management routes
 */
import type { useNavigate } from '@tanstack/react-router'
import type { Command } from '../CommandPalette'
import type { ViewMode } from './types'

interface UseTeamCommandsArgs {
  // View / layout
  viewMode: ViewMode
  cycleViewMode: () => void
  setViewMode: (m: ViewMode) => void
  setShowAgentSidebar: (fn: (v: boolean) => boolean) => void
  setShowFilesPanel: (fn: (v: boolean) => boolean) => void
  setShowTodos: (fn: (v: boolean) => boolean) => void

  // Session
  handleNewSession: () => void

  // Dream
  handleDreamRun: () => void

  // Agents
  agentNames: string[]
  leadName: string | null
  openAgents: string[]
  focusedAgent: string | null
  cycleActiveAgent: (dir: 'next' | 'prev') => void
  setActiveAgent: (name: string) => void
  focusAgent: (name: string) => void
  openAgent: (name: string) => void

  // Unified-mode split
  handleSplitDown: () => void
  handleSplitRight: () => void
  handleClosePane: () => void

  // Navigation
  navigate: ReturnType<typeof useNavigate>
}

export function useTeamCommands({
  viewMode,
  cycleViewMode,
  setViewMode,
  setShowAgentSidebar,
  setShowFilesPanel,
  setShowTodos,
  handleNewSession,
  handleDreamRun,
  agentNames,
  leadName,
  openAgents,
  focusedAgent,
  cycleActiveAgent,
  setActiveAgent,
  focusAgent,
  openAgent,
  handleSplitDown,
  handleSplitRight,
  handleClosePane,
  navigate,
}: UseTeamCommandsArgs): Command[] {
  const commands: Command[] = [
    { id: 'new-chat', group: 'Team', label: 'New Team Chat', description: 'Start a fresh team conversation', shortcut: 'Ctrl+N', action: handleNewSession },
    { id: 'dream-run', group: 'Team', label: 'Run Dream', description: 'Synthesise unprocessed sessions into wiki topics', action: handleDreamRun },
    {
      id: 'toggle-view', group: 'View',
      label: viewMode === 'agent' ? 'Switch to Split View' : viewMode === 'split' ? 'Switch to Unified View' : 'Switch to Agent View',
      description: 'Cycle: Agent → Split → Unified', shortcut: 'Ctrl+V', action: cycleViewMode,
    },
    ...(viewMode === 'unified' ? [
      { id: 'split-down',  group: 'View', label: 'Split Pane Down',  description: 'Open next agent below focused pane',          shortcut: 'Ctrl+J', action: handleSplitDown },
      { id: 'split-right', group: 'View', label: 'Split Pane Right', description: 'Open next agent to the right of focused pane', shortcut: 'Ctrl+K', action: handleSplitRight },
      { id: 'close-pane',  group: 'View', label: 'Close Focused Pane', description: 'Minimize the focused agent pane',             shortcut: 'Ctrl+W', action: handleClosePane },
    ] : []),
    { id: 'agent-info',       group: 'View',       label: 'Agent Capabilities', description: 'Show agent tools, skills and config', shortcut: 'Ctrl+A', action: () => setShowAgentSidebar((v) => !v) },
    { id: 'todos',            group: 'View',       label: 'Task List',          description: 'View agent todos and progress', shortcut: 'Ctrl+T', action: () => setShowTodos((v) => !v) },
    { id: 'workspace-files',  group: 'View',       label: 'Toggle Workspace Files', description: 'Browse files the agent has produced', shortcut: 'Ctrl+F', action: () => setShowFilesPanel((v) => !v) },
    { id: 'collapse-sidebar', group: 'View',       label: 'Toggle Sidebar',    description: '', shortcut: 'Ctrl+B', action: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', ctrlKey: true, bubbles: true })) },
    { id: 'wiki',             group: 'View',       label: 'Wiki',              description: 'Browse and edit the agent wiki', shortcut: 'Ctrl+M', action: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'm', ctrlKey: true, bubbles: true })) },
    { id: 'scheduled-tasks',  group: 'View',       label: 'Scheduled Tasks',   description: 'Manage cron and scheduled agent tasks', shortcut: 'Ctrl+S', action: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true, bubbles: true })) },
    { id: 'focus-input',      group: 'View',       label: 'Focus Chat Input',  description: 'Jump cursor to the message composer', shortcut: 'Ctrl+I', action: () => window.dispatchEvent(new CustomEvent('focus-chat-input')) },
    ...agentNames.map((name) => ({
      id: `switch-${name}`, group: 'Agents',
      label: viewMode === 'unified'
        ? (openAgents.includes(name) ? `Focus ${name}` : `Open ${name}`)
        : `View ${name}`,
      description: name === leadName ? 'Lead agent' : 'Worker agent',
      action: () => {
        if (viewMode === 'unified') {
          if (openAgents.includes(name)) focusAgent(name); else openAgent(name)
        } else {
          setViewMode('agent'); setActiveAgent(name)
        }
      },
    })),
    { id: 'next-agent', group: 'Agents', label: 'Next Agent',     description: 'Tab',       action: () => viewMode === 'unified' ? focusAgent(openAgents[(openAgents.indexOf(focusedAgent ?? '') + 1) % openAgents.length]) : cycleActiveAgent('next') },
    { id: 'prev-agent', group: 'Agents', label: 'Previous Agent', description: 'Shift+Tab', action: () => viewMode === 'unified' ? focusAgent(openAgents[(openAgents.indexOf(focusedAgent ?? '') - 1 + openAgents.length) % openAgents.length]) : cycleActiveAgent('prev') },
    { id: 'go-home',     group: 'Navigation', label: 'Go to Home',     description: '', action: () => navigate({ to: '/' }) },
    { id: 'go-settings', group: 'Navigation', label: 'Open Settings',  description: 'Manage agents & skills', action: () => navigate({ to: '/settings/agents' }) },
    { id: 'settings-agents', group: 'Settings', label: 'Manage Agents', description: 'Edit agent .md files',  action: () => navigate({ to: '/settings/agents' }) },
    { id: 'settings-new-agent', group: 'Settings', label: 'New Agent',  description: 'Create a new agent',    action: () => navigate({ to: '/settings/agents/new' }) },
    { id: 'settings-skills', group: 'Settings', label: 'Manage Skills', description: 'Edit skill .md files',  action: () => navigate({ to: '/settings/skills' }) },
    { id: 'settings-new-skill', group: 'Settings', label: 'New Skill',  description: 'Create a new skill',    action: () => navigate({ to: '/settings/skills/new' }) },
    { id: 'settings-dream', group: 'Settings', label: 'Dream Config',  description: 'Edit the dream agent prompt and schedule', action: () => navigate({ to: '/settings/dream' }) },
    ...agentNames.map((name) => ({
      id: `edit-${name}`, group: 'Settings',
      label: `Edit ${name}…`,
      description: 'Jump to agent editor',
      action: () => navigate({ to: '/settings/agents/$name', params: { name } }),
    })),
  ]
  return commands
}
