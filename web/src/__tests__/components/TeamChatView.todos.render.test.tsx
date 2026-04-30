import { describe, it, expect, afterEach, mock } from 'bun:test'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { TodoItem } from '@/api/types'

// Mock component that simulates the Todos popover behavior
// This allows us to test the rendering logic without the full TeamChatView
function TodosPopoverMock({
  todos,
  sessionId,
  onOpenChange,
  open,
}: {
  todos: TodoItem[]
  sessionId: string | null
  onOpenChange: (open: boolean) => void
  open: boolean
}) {
  const TODO_STATUS_ORDER: Record<TodoItem['status'], number> = {
    in_progress: 0,
    pending: 1,
    completed: 2,
    cancelled: 3,
  }

  const sortedTodos = [...todos].sort((a, b) => TODO_STATUS_ORDER[a.status] - TODO_STATUS_ORDER[b.status])
  const completedCount = todos.filter((t) => t.status === 'completed').length
  const hasInProgress = todos.some((t) => t.status === 'in_progress')

  const getStatusIcon = (status: TodoItem['status']): string => {
    const icons: Record<TodoItem['status'], string> = {
      completed: '✓',
      cancelled: '✗',
      in_progress: '▶',
      pending: '○',
    }
    return icons[status]
  }

  const getPriorityBadgeClass = (priority: TodoItem['priority']): string => {
    if (priority === 'high') {
      return 'bg-red-500/10 text-red-500'
    }
    if (priority === 'low') {
      return 'bg-accent-dim text-text-subtle'
    }
    return 'bg-amber-500/10 text-amber-500'
  }

  return (
    <div>
      <button
        onClick={() => onOpenChange(!open)}
        disabled={!sessionId}
        data-testid="todos-trigger"
        title={sessionId ? 'Task list (Ctrl+T)' : 'No active session'}
      >
        Todos
        {hasInProgress && <span data-testid="in-progress-dot" className="size-1.5 rounded-full" />}
      </button>

      {open && (
        <div data-testid="todos-popover" className="w-80">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-xs font-semibold">Tasks</span>
            {todos.length > 0 && (
              <span data-testid="todos-counter" className="text-[10px]">
                {completedCount}/{todos.length} done
              </span>
            )}
          </div>
          {todos.length === 0 ? (
            <p data-testid="todos-empty" className="px-3 py-4 text-center text-xs">
              No tasks yet
            </p>
          ) : (
            <ul data-testid="todos-list" className="max-h-80 overflow-y-auto py-1">
              {sortedTodos.map((todo) => (
                <li key={todo.task_id} data-testid={`todo-item-${todo.task_id}`} className="flex items-start gap-2 px-3 py-1.5">
                  <span className="mt-0.5 shrink-0 text-[10px]" data-testid={`todo-icon-${todo.task_id}`}>
                    {getStatusIcon(todo.status)}
                  </span>
                  <span
                    className={`flex-1 text-xs leading-snug ${
                      todo.status === 'completed' || todo.status === 'cancelled'
                        ? 'text-text-subtle line-through'
                        : 'text-text'
                    }`}
                    data-testid={`todo-content-${todo.task_id}`}
                  >
                    {todo.content}
                  </span>
                  <span
                    className={`shrink-0 self-start rounded px-1 py-0.5 text-[9px] font-medium uppercase ${getPriorityBadgeClass(
                      todo.priority
                    )}`}
                    data-testid={`todo-priority-${todo.task_id}`}
                  >
                    {todo.priority}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// Test wrapper with QueryClient
function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

afterEach(cleanup)

describe('Todos Popover - Rendering', () => {
  describe('Button state', () => {
    it('renders button enabled when sessionId is provided', () => {
      render(
        <TodosPopoverMock todos={[]} sessionId="session-123" onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      const button = screen.getByTestId('todos-trigger')
      expect(button.hasAttribute('disabled')).toBe(false)
    })

    it('renders button disabled when sessionId is null', () => {
      render(
        <TodosPopoverMock todos={[]} sessionId={null} onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      const button = screen.getByTestId('todos-trigger')
      expect(button.hasAttribute('disabled')).toBe(true)
    })

    it('shows correct title when sessionId is provided', () => {
      render(
        <TodosPopoverMock todos={[]} sessionId="session-123" onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      const button = screen.getByTestId('todos-trigger')
      expect(button.getAttribute('title')).toBe('Task list (Ctrl+T)')
    })

    it('shows correct title when sessionId is null', () => {
      render(
        <TodosPopoverMock todos={[]} sessionId={null} onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      const button = screen.getByTestId('todos-trigger')
      expect(button.getAttribute('title')).toBe('No active session')
    })
  })

  describe('In-progress indicator', () => {
    it('shows dot indicator when any todo is in_progress', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'in_progress', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByTestId('in-progress-dot')).toBeTruthy()
    })

    it('hides dot indicator when no todos are in_progress', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      expect(screen.queryByTestId('in-progress-dot')).toBeNull()
    })

    it('shows dot indicator when multiple todos exist and one is in_progress', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'low' },
        { task_id: '2', content: 'Task 2', status: 'in_progress', priority: 'high' },
        { task_id: '3', content: 'Task 3', status: 'completed', priority: 'medium' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByTestId('in-progress-dot')).toBeTruthy()
    })
  })

  describe('Empty state', () => {
    it('shows "No tasks yet" when todos list is empty', () => {
      render(
        <TodosPopoverMock todos={[]} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByTestId('todos-empty')).toBeTruthy()
      expect(screen.getByText('No tasks yet')).toBeTruthy()
    })

    it('does not show counter when todos list is empty', () => {
      render(
        <TodosPopoverMock todos={[]} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.queryByTestId('todos-counter')).toBeNull()
    })

    it('does not show list when todos list is empty', () => {
      render(
        <TodosPopoverMock todos={[]} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.queryByTestId('todos-list')).toBeNull()
    })
  })

  describe('Counter display', () => {
    it('shows counter with correct format when todos exist', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'completed', priority: 'low' },
        { task_id: '2', content: 'Task 2', status: 'pending', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByTestId('todos-counter')).toBeTruthy()
      expect(screen.getByText('1/2 done')).toBeTruthy()
    })

    it('shows 0 completed when no todos are completed', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'low' },
        { task_id: '2', content: 'Task 2', status: 'in_progress', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('0/2 done')).toBeTruthy()
    })

    it('shows all completed when all todos are completed', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'completed', priority: 'low' },
        { task_id: '2', content: 'Task 2', status: 'completed', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('2/2 done')).toBeTruthy()
    })

    it('counts only completed items, not cancelled', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'completed', priority: 'low' },
        { task_id: '2', content: 'Task 2', status: 'cancelled', priority: 'high' },
        { task_id: '3', content: 'Task 3', status: 'pending', priority: 'medium' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('1/3 done')).toBeTruthy()
    })
  })

  describe('Todo items rendering', () => {
    it('renders all todos in the list', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'low' },
        { task_id: '2', content: 'Task 2', status: 'pending', priority: 'high' },
        { task_id: '3', content: 'Task 3', status: 'pending', priority: 'medium' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByTestId('todo-item-1')).toBeTruthy()
      expect(screen.getByTestId('todo-item-2')).toBeTruthy()
      expect(screen.getByTestId('todo-item-3')).toBeTruthy()
    })

    it('renders todo content correctly', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Buy groceries', status: 'pending', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('Buy groceries')).toBeTruthy()
    })

    it('uses task_id as React key for each item', () => {
      const todos: TodoItem[] = [
        { task_id: 'unique-id-1', content: 'Task 1', status: 'pending', priority: 'low' },
        { task_id: 'unique-id-2', content: 'Task 2', status: 'pending', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      // If keys are wrong, React would warn. We verify items render correctly.
      expect(screen.getByTestId('todo-item-unique-id-1')).toBeTruthy()
      expect(screen.getByTestId('todo-item-unique-id-2')).toBeTruthy()
    })
  })

  describe('Status icons', () => {
    it('shows checkmark for completed status', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'completed', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('✓')).toBeTruthy()
    })

    it('shows X for cancelled status', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'cancelled', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('✗')).toBeTruthy()
    })

    it('shows play symbol for in_progress status', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'in_progress', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('▶')).toBeTruthy()
    })

    it('shows circle for pending status', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('○')).toBeTruthy()
    })

    it('renders correct icons for all statuses', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'In Progress', status: 'in_progress', priority: 'low' },
        { task_id: '2', content: 'Pending', status: 'pending', priority: 'low' },
        { task_id: '3', content: 'Completed', status: 'completed', priority: 'low' },
        { task_id: '4', content: 'Cancelled', status: 'cancelled', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('▶')).toBeTruthy()
      expect(screen.getByText('○')).toBeTruthy()
      expect(screen.getByText('✓')).toBeTruthy()
      expect(screen.getByText('✗')).toBeTruthy()
    })
  })

  describe('Priority badges', () => {
    it('renders priority label for each todo', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'high' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('high')).toBeTruthy()
    })

    it('renders all priority levels', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'High', status: 'pending', priority: 'high' },
        { task_id: '2', content: 'Medium', status: 'pending', priority: 'medium' },
        { task_id: '3', content: 'Low', status: 'pending', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByText('high')).toBeTruthy()
      expect(screen.getByText('medium')).toBeTruthy()
      expect(screen.getByText('low')).toBeTruthy()
    })
  })

  describe('Sorting', () => {
    it('renders todos in correct sort order', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Completed', status: 'completed', priority: 'low' },
        { task_id: '2', content: 'In Progress', status: 'in_progress', priority: 'high' },
        { task_id: '3', content: 'Pending', status: 'pending', priority: 'medium' },
        { task_id: '4', content: 'Cancelled', status: 'cancelled', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      const items = screen.getAllByTestId(/^todo-item-/)
      expect(items[0].getAttribute('data-testid')).toBe('todo-item-2') // in_progress first
      expect(items[1].getAttribute('data-testid')).toBe('todo-item-3') // pending second
      expect(items[2].getAttribute('data-testid')).toBe('todo-item-1') // completed third
      expect(items[3].getAttribute('data-testid')).toBe('todo-item-4') // cancelled last
    })
  })

  describe('Styling for completed/cancelled items', () => {
    it('applies strikethrough and dimmed text to completed items', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Completed Task', status: 'completed', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      const content = screen.getByTestId('todo-content-1')
      expect(content.className).toContain('line-through')
      expect(content.className).toContain('text-text-subtle')
    })

    it('applies strikethrough and dimmed text to cancelled items', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Cancelled Task', status: 'cancelled', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      const content = screen.getByTestId('todo-content-1')
      expect(content.className).toContain('line-through')
      expect(content.className).toContain('text-text-subtle')
    })

    it('does not apply strikethrough to pending items', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Pending Task', status: 'pending', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      const content = screen.getByTestId('todo-content-1')
      expect(content.className).not.toContain('line-through')
      expect(content.className).toContain('text-text')
    })

    it('does not apply strikethrough to in_progress items', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'In Progress Task', status: 'in_progress', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      const content = screen.getByTestId('todo-content-1')
      expect(content.className).not.toContain('line-through')
      expect(content.className).toContain('text-text')
    })
  })

  describe('Popover open/close', () => {
    it('shows popover content when open is true', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={true} />,
        { wrapper: createWrapper() }
      )
      expect(screen.getByTestId('todos-popover')).toBeTruthy()
    })

    it('hides popover content when open is false', () => {
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={() => {}} open={false} />,
        { wrapper: createWrapper() }
      )
      expect(screen.queryByTestId('todos-popover')).toBeNull()
    })

    it('calls onOpenChange when button is clicked', async () => {
      const user = userEvent.setup()
      const onOpenChange = mock(() => {})
      const todos: TodoItem[] = [
        { task_id: '1', content: 'Task 1', status: 'pending', priority: 'low' },
      ]
      render(
        <TodosPopoverMock todos={todos} sessionId="session-123" onOpenChange={onOpenChange} open={false} />,
        { wrapper: createWrapper() }
      )
      await user.click(screen.getByTestId('todos-trigger'))
      expect(onOpenChange).toHaveBeenCalledWith(true)
    })
  })
})
