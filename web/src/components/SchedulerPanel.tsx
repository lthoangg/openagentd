/**
 * SchedulerPanel — modal overlay for managing scheduled tasks.
 *
 * Mirrors MemoryPanel structure: fixed overlay with right-sliding drawer,
 * backdrop click to close, and X close button.
 */

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Clock, Play, Pause, Trash2, Plus, Loader2, AlertCircle, CalendarClock, Zap, ArrowLeft, Pencil } from 'lucide-react'
import { format } from 'date-fns'
import { DateTimePicker } from '@/components/ui/date-time-picker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  useScheduledTasksQuery,
  useCreateScheduledTaskMutation,
  useUpdateScheduledTaskMutation,
  useDeleteScheduledTaskMutation,
  usePauseScheduledTaskMutation,
  useResumeScheduledTaskMutation,
  useTriggerScheduledTaskMutation,
  useTeamAgentsQuery,
} from '@/queries'
import type { ScheduledTaskResponse, ScheduledTaskCreate } from '@/api/types'
import { formatRelativeDate } from '@/utils/format'
import { useIsMobile } from '@/hooks/use-mobile'

interface SchedulerPanelProps {
  open: boolean
  onClose: () => void
}

// ── Shared utility ──────────────────────────────────────────────────────────

function formatScheduleLabel(task: Pick<ScheduledTaskResponse, 'schedule_type' | 'at_datetime' | 'every_seconds' | 'cron_expression'>): string {
  if (task.schedule_type === 'at' && task.at_datetime) {
    return `at ${format(new Date(task.at_datetime), 'dd/MM/yyyy HH:mm')}`
  }
  if (task.schedule_type === 'every' && task.every_seconds) {
    const mins = Math.floor(task.every_seconds / 60)
    const secs = task.every_seconds % 60
    if (mins > 0 && secs === 0) return `every ${mins}m`
    if (mins === 0) return `every ${secs}s`
    return `every ${mins}m ${secs}s`
  }
  if (task.schedule_type === 'cron' && task.cron_expression) {
    return `cron: ${task.cron_expression}`
  }
  return 'unknown schedule'
}

// ── Panel root ──────────────────────────────────────────────────────────────

export function SchedulerPanel({ open, onClose }: SchedulerPanelProps) {
  const isMobile = useIsMobile()

  // Ephemeral panel-scoped state — not shared outside this component tree,
  // so useState is correct here (no need for Zustand).
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  // Mobile: 'list' | 'detail' | 'create'
  const [mobilePane, setMobilePane] = useState<'list' | 'detail' | 'create'>('list')

  const tasksQuery = useScheduledTasksQuery()
  const agentsQuery = useTeamAgentsQuery()

  const tasks = tasksQuery.data?.tasks ?? []
  const agents = agentsQuery.data?.agents ?? []

  const filteredTasks = tasks.filter(
    (task) =>
      task.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      task.agent.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const selectedTask = selectedTaskId ? tasks.find((t) => t.id === selectedTaskId) : null

  const handleSelectTask = (id: string) => {
    setSelectedTaskId(id)
    if (isMobile) setMobilePane('detail')
  }

  const handleCloseDetail = () => {
    setSelectedTaskId(null)
    if (isMobile) setMobilePane('list')
  }

  const handleOpenCreate = () => {
    if (isMobile) setMobilePane('create')
  }

  const handleBackToList = () => {
    setMobilePane('list')
  }

  // On mobile: show list OR detail/create — never both side-by-side.
  const showList = !isMobile || mobilePane === 'list'
  const showDetail = !isMobile || mobilePane === 'detail' || mobilePane === 'create'

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
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
            className="fixed inset-y-0 right-0 z-50 flex w-[min(960px,90vw)] flex-col overflow-hidden bg-(--color-surface) shadow-2xl"
          >
            {/* Header */}
            <header className="flex items-center justify-between border-b border-(--color-border) px-4 py-3">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                {/* Mobile back button — shown in detail/create pane */}
                {isMobile && mobilePane !== 'list' && (
                  <button
                    onClick={handleBackToList}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text)"
                    aria-label="Back to task list"
                  >
                    <ArrowLeft size={14} />
                  </button>
                )}
                <div className="flex min-w-0 items-center gap-2">
                  <CalendarClock size={18} className="shrink-0 text-(--color-accent)" />
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-(--color-text)">
                      {isMobile && mobilePane === 'detail' && selectedTask
                        ? selectedTask.name
                        : isMobile && mobilePane === 'create'
                          ? 'Create Task'
                          : 'Scheduled Tasks'}
                    </h2>
                    {(!isMobile || mobilePane === 'list') && (
                      <p className="text-xs text-(--color-text-subtle)">
                        Manage cron and scheduled agent tasks
                      </p>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {/* Mobile: Create button shown in list pane */}
                {isMobile && mobilePane === 'list' && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={handleOpenCreate}
                    aria-label="Create new task"
                    title="Create task"
                  >
                    <Plus size={16} />
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={onClose}
                  aria-label="Close scheduler panel"
                >
                  <X size={16} />
                </Button>
              </div>
            </header>

            {/* Main content */}
            <div className="flex flex-1 overflow-hidden">
              {/* List panel */}
              {showList && (
                <div className={`flex flex-col border-r border-(--color-border) ${isMobile ? 'w-full' : 'w-96 shrink-0'}`}>
                  {/* Search bar */}
                  <div className="border-b border-(--color-border) p-3">
                    <Input
                      placeholder="Search tasks…"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                  </div>

                  {/* Task list */}
                  <div className="flex-1 overflow-y-auto">
                    {tasksQuery.isLoading ? (
                      <div className="flex items-center justify-center p-8">
                        <Loader2 size={20} className="animate-spin text-(--color-text-muted)" />
                      </div>
                    ) : tasksQuery.isError ? (
                      <div className="flex flex-col items-center justify-center gap-2 p-8 text-center">
                        <AlertCircle size={20} className="text-(--color-error)" />
                        <p className="text-sm text-(--color-text-muted)">Failed to load tasks</p>
                      </div>
                    ) : filteredTasks.length === 0 ? (
                      <div className="flex flex-col items-center justify-center gap-2 p-8 text-center">
                        <Clock size={20} className="text-(--color-text-muted)" />
                        <p className="text-sm text-(--color-text-muted)">
                          {searchQuery ? 'No tasks match your search' : 'No scheduled tasks yet'}
                        </p>
                        {!searchQuery && !isMobile && (
                          <p className="text-xs text-(--color-text-subtle)">
                            Use the form on the right to create one.
                          </p>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-1 p-2">
                        {filteredTasks.map((task) => (
                          <TaskListItem
                            key={task.id}
                            task={task}
                            isSelected={selectedTaskId === task.id}
                            onSelect={() => handleSelectTask(task.id)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Detail / Create panel */}
              {showDetail && (
                <div className="flex flex-1 flex-col overflow-hidden">
                  {selectedTask && (!isMobile || mobilePane === 'detail') ? (
                    <TaskDetailView
                      task={selectedTask}
                      agents={agents}
                      onClose={handleCloseDetail}
                    />
                  ) : (
                    <CreateTaskForm agents={agents} onSuccess={handleCloseDetail} />
                  )}
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

// ── Task list item ──────────────────────────────────────────────────────────

function TaskListItem({
  task,
  isSelected,
  onSelect,
}: {
  task: ScheduledTaskResponse
  isSelected: boolean
  onSelect: () => void
}) {
  const deleteMutation = useDeleteScheduledTaskMutation()
  const pauseMutation = usePauseScheduledTaskMutation()
  const resumeMutation = useResumeScheduledTaskMutation()
  const triggerMutation = useTriggerScheduledTaskMutation()

  const statusColor = {
    pending: 'text-(--color-text-muted)',
    running: 'text-(--color-accent)',
    paused: 'text-(--color-warning)',
    completed: 'text-(--color-success)',
    failed: 'text-(--color-error)',
  }[task.status] ?? 'text-(--color-text-muted)'

  return (
    <button
      onClick={onSelect}
      className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
        isSelected
          ? 'border-(--color-accent) bg-(--color-accent-subtle)'
          : 'border-(--color-border) bg-(--color-surface-2) hover:border-(--color-border-strong)'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-(--color-text)">{task.name}</p>
          <p className="mt-0.5 truncate text-xs text-(--color-text-muted)">
            {formatScheduleLabel(task)}
          </p>
          <div className="mt-1 flex items-center gap-2">
            <span className="inline-block rounded-full bg-(--color-accent-subtle) px-2 py-0.5 text-xs text-(--color-accent)">
              {task.agent}
            </span>
            <span className={`text-xs font-medium ${statusColor}`}>{task.status}</span>
          </div>
          {task.last_error && (
            <p className="mt-1 truncate text-xs text-(--color-error)">{task.last_error}</p>
          )}
          {task.next_fire_at && (
            <p className="mt-1 text-xs text-(--color-text-muted)">
              Next: {formatRelativeDate(task.next_fire_at)}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex shrink-0 gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={(e) => {
              e.stopPropagation()
              triggerMutation.mutate(task.id)
            }}
            disabled={triggerMutation.isPending}
            title="Trigger now"
          >
            {triggerMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Zap size={14} />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={(e) => {
              e.stopPropagation()
              if (task.status === 'paused') {
                resumeMutation.mutate(task.id)
              } else {
                pauseMutation.mutate(task.id)
              }
            }}
            disabled={pauseMutation.isPending || resumeMutation.isPending}
            title={task.status === 'paused' ? 'Resume' : 'Pause'}
          >
            {pauseMutation.isPending || resumeMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : task.status === 'paused' ? (
              <Play size={14} />
            ) : (
              <Pause size={14} />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={(e) => {
              e.stopPropagation()
              if (confirm(`Delete task "${task.name}"?`)) {
                deleteMutation.mutate(task.id)
              }
            }}
            disabled={deleteMutation.isPending}
            title="Delete"
            className="hover:bg-(--color-error-subtle) hover:text-(--color-error)"
          >
            {deleteMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
          </Button>
        </div>
      </div>
    </button>
  )
}

// ── Create task form ────────────────────────────────────────────────────────

function CreateTaskForm({
  agents,
  onSuccess,
}: {
  agents: Array<{ name: string }>
  onSuccess: () => void
}) {
  const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [formData, setFormData] = useState<ScheduledTaskCreate>({
    name: '',
    agent: agents[0]?.name ?? '',
    schedule_type: 'every',
    every_seconds: 3600,
    timezone: localTz,
    prompt: '',
    enabled: true,
  })
  const [error, setError] = useState<string | null>(null)

  const createMutation = useCreateScheduledTaskMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!formData.name.trim()) { setError('Task name is required'); return }
    if (!formData.agent) { setError('Agent is required'); return }
    if (!formData.prompt.trim()) { setError('Prompt is required'); return }
    if (formData.schedule_type === 'at' && !formData.at_datetime) {
      setError('Date/time is required for "at" schedule'); return
    }
    if (formData.schedule_type === 'every' && (!formData.every_seconds || formData.every_seconds <= 0)) {
      setError('Interval must be greater than 0'); return
    }
    if (formData.schedule_type === 'cron' && !formData.cron_expression?.trim()) {
      setError('Cron expression is required'); return
    }

    // Strip fields that don't belong to the active schedule_type.
    // The backend Pydantic validator rejects any extra schedule fields
    // (e.g. every_seconds present when schedule_type='at').
    const payload: ScheduledTaskCreate = {
      name: formData.name.trim(),
      agent: formData.agent,
      schedule_type: formData.schedule_type,
      timezone: formData.timezone,
      prompt: formData.prompt.trim(),
      session_id: formData.session_id,
      enabled: formData.enabled,
      ...(formData.schedule_type === 'at'    ? { at_datetime: formData.at_datetime }          : {}),
      ...(formData.schedule_type === 'every' ? { every_seconds: formData.every_seconds }       : {}),
      ...(formData.schedule_type === 'cron'  ? { cron_expression: formData.cron_expression }   : {}),
    }

    createMutation.mutate(payload, {
      onSuccess: () => {
        setFormData({
          name: '',
          agent: agents[0]?.name ?? '',
          schedule_type: 'every',
          every_seconds: 3600,
          timezone: localTz,
          prompt: '',
          enabled: true,
        })
        onSuccess()
      },
      onError: (err) => {
        setError(err instanceof Error ? err.message : 'Failed to create task')
      },
    })
  }

  return (
    <div className="flex flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-(--color-border) px-6 py-4">
        <div className="flex items-center gap-2">
          <Plus size={18} className="text-(--color-accent)" />
          <h2 className="text-lg font-semibold text-(--color-text)">Create Task</h2>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-y-auto p-6">
        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Task Name</label>
            <Input
              className="mt-1"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g., Daily Report"
            />
          </div>

          {/* Agent */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Agent</label>
            <Select
              value={formData.agent ?? ''}
              onValueChange={(v) => { if (v) setFormData({ ...formData, agent: v }) }}
            >
              <SelectTrigger className="mt-1 w-full">
                <SelectValue placeholder="Select agent" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.name} value={agent.name}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Schedule Type */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Schedule Type</label>
            <Tabs
              value={formData.schedule_type}
              onValueChange={(v) =>
                setFormData({ ...formData, schedule_type: v as ScheduledTaskCreate['schedule_type'] })
              }
              className="mt-2"
            >
              <TabsList className="w-full">
                <TabsTrigger value="every" className="flex-1">Every</TabsTrigger>
                <TabsTrigger value="cron" className="flex-1">Cron</TabsTrigger>
                <TabsTrigger value="at" className="flex-1">At</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Schedule value (conditional) */}
          {formData.schedule_type === 'at' && (
            <div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-(--color-text)">Date & Time</label>
                  <div className="mt-1">
                    <DateTimePicker
                      value={formData.at_datetime ?? ''}
                      onChange={(v) => setFormData({ ...formData, at_datetime: v })}
                    />
                  </div>
                </div>
                <div className="w-44 shrink-0">
                  <label className="block text-sm font-medium text-(--color-text)">Timezone</label>
                  <Input
                    className="mt-1"
                    value={formData.timezone}
                    onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                    placeholder={localTz}
                  />
                </div>
              </div>
              <p className="mt-1 text-xs text-(--color-text-muted)">IANA timezone (e.g., America/New_York)</p>
            </div>
          )}

          {formData.schedule_type === 'every' && (
            <div>
              <label className="block text-sm font-medium text-(--color-text)">Interval (seconds)</label>
              <Input
                className="mt-1"
                type="number"
                min="1"
                value={formData.every_seconds ?? 3600}
                onChange={(e) =>
                  setFormData({ ...formData, every_seconds: parseInt(e.target.value) || 0 })
                }
              />
              <p className="mt-1 text-xs text-(--color-text-muted)">e.g., 3600 = 1 hour, 86400 = 1 day</p>
            </div>
          )}

          {formData.schedule_type === 'cron' && (
            <div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-(--color-text)">Cron Expression</label>
                  <Input
                    className="mt-1"
                    value={formData.cron_expression ?? ''}
                    onChange={(e) => setFormData({ ...formData, cron_expression: e.target.value })}
                    placeholder="e.g., 0 9 * * MON-FRI"
                  />
                </div>
                <div className="w-44 shrink-0">
                  <label className="block text-sm font-medium text-(--color-text)">Timezone</label>
                  <Input
                    className="mt-1"
                    value={formData.timezone}
                    onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                    placeholder={localTz}
                  />
                </div>
              </div>
              <p className="mt-1 text-xs text-(--color-text-muted)">IANA timezone (e.g., America/New_York)</p>
            </div>
          )}

          {/* Prompt */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Prompt</label>
            <Textarea
              className="mt-1"
              value={formData.prompt}
              onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
              placeholder="What should the agent do?"
              rows={4}
            />
          </div>

          {/* Session ID */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Session ID (optional)</label>
            <Input
              className="mt-1"
              value={formData.session_id ?? ''}
              onChange={(e) => setFormData({ ...formData, session_id: e.target.value || null })}
              placeholder="Leave blank for new session, or enter 'auto'"
            />
            <p className="mt-1 text-xs text-(--color-text-muted)">
              null = new session each run, "auto" = persistent session, or UUID
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="flex gap-2 rounded-lg border border-(--color-error) bg-(--color-error-subtle) p-3">
              <AlertCircle size={16} className="shrink-0 text-(--color-error)" />
              <p className="text-sm text-(--color-error)">{error}</p>
            </div>
          )}
        </div>

        {/* Submit */}
        <Button
          type="submit"
          disabled={createMutation.isPending}
          className="mt-6 w-full"
        >
          {createMutation.isPending ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Creating…
            </>
          ) : (
            <>
              <Plus size={14} />
              Create Task
            </>
          )}
        </Button>
      </form>
    </div>
  )
}

// ── Task detail view ────────────────────────────────────────────────────────

function TaskDetailView({
  task,
  agents,
  onClose,
}: {
  task: ScheduledTaskResponse
  agents: Array<{ name: string }>
  onClose: () => void
}) {
  const [editing, setEditing] = useState(false)

  if (editing) {
    return (
      <EditTaskForm
        task={task}
        agents={agents}
        onSuccess={() => setEditing(false)}
        onCancel={() => setEditing(false)}
      />
    )
  }

  const statusColor = {
    pending: 'text-(--color-text-muted)',
    running: 'text-(--color-accent)',
    paused: 'text-(--color-warning)',
    completed: 'text-(--color-success)',
    failed: 'text-(--color-error)',
  }[task.status] ?? 'text-(--color-text-muted)'

  return (
    <div className="flex flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-(--color-border) px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-semibold text-(--color-text)">{task.name}</h2>
            <p className="mt-1 text-sm text-(--color-text-muted)">{formatScheduleLabel(task)}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button variant="ghost" size="icon-sm" onClick={() => setEditing(true)} title="Edit task">
              <Pencil size={16} />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={onClose} title="Close">
              <X size={16} />
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="space-y-6">
          {/* Status section */}
          <div>
            <h3 className="text-sm font-semibold text-(--color-text)">Status</h3>
            <div className="mt-2 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-(--color-text-muted)">Current</span>
                <span className={`text-sm font-medium ${statusColor}`}>{task.status}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-(--color-text-muted)">Enabled</span>
                <span className="text-sm text-(--color-text)">{task.enabled ? 'Yes' : 'No'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-(--color-text-muted)">Run Count</span>
                <span className="text-sm text-(--color-text)">{task.run_count}</span>
              </div>
            </div>
          </div>

          {/* Schedule section */}
          <div>
            <h3 className="text-sm font-semibold text-(--color-text)">Schedule</h3>
            <div className="mt-2 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-(--color-text-muted)">Type</span>
                <span className="text-sm text-(--color-text) capitalize">{task.schedule_type}</span>
              </div>
              {task.schedule_type === 'at' && task.at_datetime && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-(--color-text-muted)">Date/Time</span>
                  <span className="text-sm text-(--color-text)">
                    {format(new Date(task.at_datetime), 'dd/MM/yyyy HH:mm')}
                  </span>
                </div>
              )}
              {task.schedule_type === 'every' && task.every_seconds && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-(--color-text-muted)">Interval</span>
                  <span className="text-sm text-(--color-text)">{task.every_seconds}s</span>
                </div>
              )}
              {task.schedule_type === 'cron' && task.cron_expression && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-(--color-text-muted)">Expression</span>
                  <span className="text-sm text-(--color-text)">{task.cron_expression}</span>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-sm text-(--color-text-muted)">Timezone</span>
                <span className="text-sm text-(--color-text)">{task.timezone}</span>
              </div>
            </div>
          </div>

          {/* Agent & Prompt section */}
          <div>
            <h3 className="text-sm font-semibold text-(--color-text)">Configuration</h3>
            <div className="mt-2 space-y-2">
              <div>
                <span className="text-sm text-(--color-text-muted)">Agent</span>
                <p className="mt-1 rounded-lg bg-(--color-surface-2) px-3 py-2 text-sm text-(--color-text)">
                  {task.agent}
                </p>
              </div>
              <div>
                <span className="text-sm text-(--color-text-muted)">Prompt</span>
                <p className="mt-1 rounded-lg bg-(--color-surface-2) px-3 py-2 text-sm text-(--color-text) whitespace-pre-wrap">
                  {task.prompt}
                </p>
              </div>
              {task.session_id && (
                <div>
                  <span className="text-sm text-(--color-text-muted)">Session ID</span>
                  <p className="mt-1 rounded-lg bg-(--color-surface-2) px-3 py-2 text-sm text-(--color-text) break-all font-mono">
                    {task.session_id}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Run history section */}
          <div>
            <h3 className="text-sm font-semibold text-(--color-text)">Run History</h3>
            <div className="mt-2 space-y-2">
              {task.last_run_at && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-(--color-text-muted)">Last Run</span>
                  <span className="text-sm text-(--color-text)">
                    {formatRelativeDate(task.last_run_at)}
                  </span>
                </div>
              )}
              {task.next_fire_at && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-(--color-text-muted)">Next Fire</span>
                  <span className="text-sm text-(--color-text)">
                    {formatRelativeDate(task.next_fire_at)}
                  </span>
                </div>
              )}
              {task.last_error && (
                <div>
                  <span className="text-sm text-(--color-text-muted)">Last Error</span>
                  <p className="mt-1 rounded-lg bg-(--color-error-subtle) px-3 py-2 text-sm text-(--color-error) whitespace-pre-wrap">
                    {task.last_error}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Timestamps */}
          <div className="border-t border-(--color-border) pt-4">
            <div className="space-y-2 text-xs text-(--color-text-muted)">
              <div>Created: {formatRelativeDate(task.created_at)}</div>
              <div>Updated: {formatRelativeDate(task.updated_at)}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Edit task form ──────────────────────────────────────────────────────────

function EditTaskForm({
  task,
  agents,
  onSuccess,
  onCancel,
}: {
  task: ScheduledTaskResponse
  agents: Array<{ name: string }>
  onSuccess: () => void
  onCancel: () => void
}) {
  const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [formData, setFormData] = useState<ScheduledTaskCreate>({
    name: task.name,
    agent: task.agent,
    schedule_type: task.schedule_type,
    at_datetime: task.at_datetime ?? undefined,
    every_seconds: task.every_seconds ?? undefined,
    cron_expression: task.cron_expression ?? undefined,
    timezone: task.timezone,
    prompt: task.prompt,
    session_id: task.session_id ?? undefined,
    enabled: task.enabled,
  })
  const [error, setError] = useState<string | null>(null)

  const updateMutation = useUpdateScheduledTaskMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!formData.agent) { setError('Agent is required'); return }
    if (!formData.prompt.trim()) { setError('Prompt is required'); return }
    if (formData.schedule_type === 'at' && !formData.at_datetime) {
      setError('Date/time is required for "at" schedule'); return
    }
    if (formData.schedule_type === 'every' && (!formData.every_seconds || formData.every_seconds <= 0)) {
      setError('Interval must be greater than 0'); return
    }
    if (formData.schedule_type === 'cron' && !formData.cron_expression?.trim()) {
      setError('Cron expression is required'); return
    }

    const payload: Partial<ScheduledTaskCreate> = {
      agent: formData.agent,
      schedule_type: formData.schedule_type,
      timezone: formData.timezone,
      prompt: formData.prompt.trim(),
      session_id: formData.session_id,
      enabled: formData.enabled,
      ...(formData.schedule_type === 'at'    ? { at_datetime: formData.at_datetime }          : {}),
      ...(formData.schedule_type === 'every' ? { every_seconds: formData.every_seconds }       : {}),
      ...(formData.schedule_type === 'cron'  ? { cron_expression: formData.cron_expression }   : {}),
    }

    updateMutation.mutate({ id: task.id, body: payload }, {
      onSuccess,
      onError: (err) => {
        setError(err instanceof Error ? err.message : 'Failed to update task')
      },
    })
  }

  return (
    <div className="flex flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-(--color-border) px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Pencil size={18} className="text-(--color-accent)" />
            <h2 className="text-lg font-semibold text-(--color-text)">Edit Task</h2>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onCancel} title="Cancel">
            <X size={16} />
          </Button>
        </div>
        <p className="mt-1 text-sm text-(--color-text-muted)">{task.name}</p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-y-auto p-6">
        <div className="space-y-4">
          {/* Agent */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Agent</label>
            <Select
              value={formData.agent ?? ''}
              onValueChange={(v) => { if (v) setFormData({ ...formData, agent: v }) }}
            >
              <SelectTrigger className="mt-1 w-full">
                <SelectValue placeholder="Select agent" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.name} value={agent.name}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Schedule Type */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Schedule Type</label>
            <Tabs
              value={formData.schedule_type}
              onValueChange={(v) =>
                setFormData({ ...formData, schedule_type: v as ScheduledTaskCreate['schedule_type'] })
              }
              className="mt-2"
            >
              <TabsList className="w-full">
                <TabsTrigger value="every" className="flex-1">Every</TabsTrigger>
                <TabsTrigger value="cron" className="flex-1">Cron</TabsTrigger>
                <TabsTrigger value="at" className="flex-1">At</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Schedule value (conditional) */}
          {formData.schedule_type === 'at' && (
            <div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-(--color-text)">Date & Time</label>
                  <div className="mt-1">
                    <DateTimePicker
                      value={formData.at_datetime ?? ''}
                      onChange={(v) => setFormData({ ...formData, at_datetime: v })}
                    />
                  </div>
                </div>
                <div className="w-44 shrink-0">
                  <label className="block text-sm font-medium text-(--color-text)">Timezone</label>
                  <Input
                    className="mt-1"
                    value={formData.timezone}
                    onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                    placeholder={localTz}
                  />
                </div>
              </div>
              <p className="mt-1 text-xs text-(--color-text-muted)">IANA timezone (e.g., America/New_York)</p>
            </div>
          )}

          {formData.schedule_type === 'every' && (
            <div>
              <label className="block text-sm font-medium text-(--color-text)">Interval (seconds)</label>
              <Input
                className="mt-1"
                type="number"
                min="1"
                value={formData.every_seconds ?? 3600}
                onChange={(e) =>
                  setFormData({ ...formData, every_seconds: parseInt(e.target.value) || 0 })
                }
              />
              <p className="mt-1 text-xs text-(--color-text-muted)">e.g., 3600 = 1 hour, 86400 = 1 day</p>
            </div>
          )}

          {formData.schedule_type === 'cron' && (
            <div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-(--color-text)">Cron Expression</label>
                  <Input
                    className="mt-1"
                    value={formData.cron_expression ?? ''}
                    onChange={(e) => setFormData({ ...formData, cron_expression: e.target.value })}
                    placeholder="e.g., 0 9 * * MON-FRI"
                  />
                </div>
                <div className="w-44 shrink-0">
                  <label className="block text-sm font-medium text-(--color-text)">Timezone</label>
                  <Input
                    className="mt-1"
                    value={formData.timezone}
                    onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                    placeholder={localTz}
                  />
                </div>
              </div>
              <p className="mt-1 text-xs text-(--color-text-muted)">IANA timezone (e.g., America/New_York)</p>
            </div>
          )}

          {/* Prompt */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Prompt</label>
            <Textarea
              className="mt-1"
              value={formData.prompt}
              onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
              placeholder="What should the agent do?"
              rows={4}
            />
          </div>

          {/* Session ID */}
          <div>
            <label className="block text-sm font-medium text-(--color-text)">Session ID (optional)</label>
            <Input
              className="mt-1"
              value={formData.session_id ?? ''}
              onChange={(e) => setFormData({ ...formData, session_id: e.target.value || undefined })}
              placeholder="Leave blank for new session, or enter 'auto'"
            />
            <p className="mt-1 text-xs text-(--color-text-muted)">
              null = new session each run, "auto" = persistent session, or UUID
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="flex gap-2 rounded-lg border border-(--color-error) bg-(--color-error-subtle) p-3">
              <AlertCircle size={16} className="shrink-0 text-(--color-error)" />
              <p className="text-sm text-(--color-error)">{error}</p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-6 flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            onClick={onCancel}
            disabled={updateMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={updateMutation.isPending}
            className="flex-1"
          >
            {updateMutation.isPending ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Saving…
              </>
            ) : (
              'Save Changes'
            )}
          </Button>
        </div>
      </form>
    </div>
  )
}
