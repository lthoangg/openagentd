/**
 * Default factory for ``AgentStream``.
 *
 * Exported as a function (not a constant) because Zustand + Immer share
 * mutable references; every agent must get its own arrays/objects so
 * that draft mutations on one agent don't bleed into another.
 */
import type { AgentStream } from './types'

export const createDefaultAgentStream = (): AgentStream => ({
  blocks: [],
  currentBlocks: [],
  currentText: '',
  currentThinking: '',
  status: 'available',
  usage: {
    promptTokens: 0,
    completionTokens: 0,
    totalTokens: 0,
    cachedTokens: 0,
  },
  _completionBase: 0,
  model: null,
  lastError: null,
})
