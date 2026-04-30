/**
 * Shared types for the TeamChatView package.
 *
 * `ViewMode` is the layout mode the user is currently in:
 *   - `agent`   — single AgentView pane for the active agent.
 *   - `split`   — fixed grid (1–6 panes) of AgentPanes; drag to reorder.
 *   - `unified` — recursive tile tree (TileArea) with split-down/right.
 *
 * `VIEW_MODES` is the rotation order used by the Ctrl+V shortcut and the
 * 3-way segmented control in the header.
 */

export type ViewMode = 'agent' | 'split' | 'unified'

export const VIEW_MODES: ViewMode[] = ['agent', 'split', 'unified']
