import type { ContentBlock } from '@/api/types'

export function generateBlockId(): string {
  return `block-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function appendThinking(
  blocks: ContentBlock[],
  text: string
): ContentBlock[] {
  const lastBlock = blocks[blocks.length - 1]

  if (lastBlock && lastBlock.type === 'thinking') {
    // Append to existing thinking block
    return [
      ...blocks.slice(0, -1),
      {
        ...lastBlock,
        content: lastBlock.content + text,
      },
    ]
  }

  // Create new thinking block
  return [
    ...blocks,
    {
      id: generateBlockId(),
      type: 'thinking',
      content: text,
    },
  ]
}

export function appendText(
  blocks: ContentBlock[],
  text: string
): ContentBlock[] {
  const lastBlock = blocks[blocks.length - 1]

  if (lastBlock && lastBlock.type === 'text') {
    // Append to existing text block
    return [
      ...blocks.slice(0, -1),
      {
        ...lastBlock,
        content: lastBlock.content + text,
      },
    ]
  }

  // Create new text block
  return [
    ...blocks,
    {
      id: generateBlockId(),
      type: 'text',
      content: text,
    },
  ]
}

/** tool_call event — first delta appearance, no args yet. Creates a pending card.
 *  If a block with this toolCallId already exists (reconnect replay), skip — no duplicate. */
export function initTool(
  blocks: ContentBlock[],
  name: string,
  toolCallId?: string,
): ContentBlock[] {
  // Me skip if already have block with same id — reconnect replay dedup
  if (toolCallId && blocks.some((b) => b.type === 'tool' && b.toolCallId === toolCallId)) {
    return blocks
  }
  return [
    ...blocks,
    {
      id: generateBlockId(),
      type: 'tool',
      content: '',
      toolName: name,
      toolArgs: undefined,
      toolDone: false,
      toolCallId,
    },
  ]
}

/** tool_start event — args assembled, execution starting. Fills in args on existing block.
 *  If block already has args (reconnect replay), skip the update — idempotent. */
export function addTool(
  blocks: ContentBlock[],
  name: string,
  args?: string,
  toolCallId?: string,
): ContentBlock[] {
  const result = [...blocks]
  // Find existing block by toolCallId first, then by name (no-args-yet pending)
  for (let i = result.length - 1; i >= 0; i--) {
    const block = result[i]
    if (
      block.type === 'tool' &&
      ((toolCallId && block.toolCallId === toolCallId) ||
        (!toolCallId && block.toolName === name && block.toolArgs === undefined))
    ) {
      // Me skip if args already set — reconnect replay dedup
      if (block.toolArgs !== undefined && block.toolArgs !== null) return result
      result[i] = { ...block, toolArgs: args }
      return result
    }
  }
  // Fallback: no matching block found (e.g. missed tool_call event) — create new
  return [
    ...blocks,
    {
      id: generateBlockId(),
      type: 'tool',
      content: '',
      toolName: name,
      toolArgs: args,
      toolDone: false,
      toolCallId,
    },
  ]
}

export function completeTool(
  blocks: ContentBlock[],
  name: string,
  toolCallId?: string,
  toolResult?: string,
): ContentBlock[] {
  const result = [...blocks]

  // 1. Prefer exact match by toolCallId (handles same tool called multiple times)
  if (toolCallId) {
    for (let i = result.length - 1; i >= 0; i--) {
      const block = result[i]
      if (block.type === 'tool' && block.toolCallId === toolCallId) {
        // Me skip if already done — reconnect replay dedup
        if (block.toolDone) return result
        result[i] = { ...block, toolDone: true, toolResult }
        return result
      }
    }
  }

  // 2. Fall back to last incomplete block matching by name
  for (let i = result.length - 1; i >= 0; i--) {
    const block = result[i]
    if (block.type === 'tool' && block.toolName === name && !block.toolDone) {
      result[i] = { ...block, toolDone: true, toolResult }
      return result
    }
  }

  return result
}
