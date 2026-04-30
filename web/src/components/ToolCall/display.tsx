/**
 * Per-tool header / args customisation.
 *
 * Most tools already have clear, short args that look fine as
 * pretty-printed JSON — adding config for them would be complexity with
 * no UX gain.  Only tools where the default JSON display is actively
 * unhelpful get customised here.
 *
 * The file mixes a component (``Arg``, kept private) with the
 * ``getToolDisplay`` registry; React Fast Refresh's "components-only"
 * rule is disabled because the component is colocated with the data it
 * decorates.
 */

/* eslint-disable react-refresh/only-export-components */

import type { ReactNode } from 'react'
import type { ToolDisplay } from './types'

/**
 * Italicise an argument value embedded in a header.
 *
 * Only argument-like values (paths, patterns, URLs, queries, recipients)
 * should be italicised — verbs and framing text stay upright.  Using a
 * dedicated component keeps the markup consistent and easy to restyle.
 */
function Arg({ children }: { children: ReactNode }) {
  return <em className="italic">{children}</em>
}

/** Extract a non-empty string field from parsed args. */
function str(parsed: Record<string, unknown>, key: string): string | null {
  const v = parsed[key]
  return typeof v === 'string' && v.trim() ? v.trim() : null
}

/** Truncate a string to maxLen chars, appending ellipsis if cut. */
function trunc(s: string, maxLen = 60): string {
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s
}

export function getToolDisplay(name: string, args: string | undefined): ToolDisplay {
  // ── date: no args, no args section ────────────────────────────────
  if (name === 'date') {
    return { header: null, headerTitle: null, formattedArgs: null }
  }

  if (!args) {
    // recall with no args — conversational header, no args section
    if (name === 'recall') {
      return { header: 'Checking memory…', headerTitle: 'Checking memory…', formattedArgs: null }
    }
    return { header: null, headerTitle: null, formattedArgs: null }
  }

  let parsed: Record<string, unknown>
  try { parsed = JSON.parse(args) } catch { return { header: null, headerTitle: null, formattedArgs: args } }

  // ── shell: description as header, command as bash block ─────────────
  if (name === 'shell') {
    const description = str(parsed, 'description')
    return {
      header: description ? <Arg>{description}</Arg> : null,
      headerTitle: description,
      formattedArgs: str(parsed, 'command'),
      language: 'bash',
    }
  }

  // ── web_search: conversational header with query ───────────────────
  if (name === 'web_search') {
    const query = str(parsed, 'query')
    const truncated = query ? trunc(query) : null
    return {
      header: truncated ? <>Searching <Arg>"{truncated}"</Arg></> : null,
      headerTitle: truncated ? `Searching "${truncated}"` : null,
      formattedArgs: query,
    }
  }

  // ── web_fetch: conversational header with domain ───────────────────
  if (name === 'web_fetch') {
    const url = str(parsed, 'url')
    let domain: string | null = null
    if (url) {
      try {
        domain = new URL(url.startsWith('http') ? url : `https://${url}`)
          .hostname.replace(/^www\./, '')
      } catch {
        domain = url
      }
    }
    const truncated = domain ? trunc(domain) : null
    return {
      header: truncated ? <>Reading <Arg>{truncated}</Arg></> : null,
      headerTitle: truncated ? `Reading ${truncated}` : null,
      formattedArgs: url,
    }
  }

  // ── remember: conversational header, list of [category] key: value ──
  if (name === 'remember') {
    const items = Array.isArray(parsed.items) ? parsed.items as Record<string, unknown>[] : []
    const lines = items.map((it) => {
      const cat = typeof it.category === 'string' ? it.category : ''
      const k = typeof it.key === 'string' ? it.key : ''
      const v = typeof it.value === 'string' ? it.value : ''
      return `[${cat}] ${k}: ${v}`
    })
    return {
      header: 'Saving to memory…',
      headerTitle: 'Saving to memory…',
      formattedArgs: lines.length > 0 ? lines.join('\n') : null,
    }
  }

  // ── forget: conversational header, list of category: key ──────────
  if (name === 'forget') {
    const items = Array.isArray(parsed.items) ? parsed.items as Record<string, unknown>[] : []
    const lines = items.map((it) => {
      const cat = typeof it.category === 'string' ? it.category : ''
      const k = typeof it.key === 'string' ? it.key : null
      return k ? `${cat}: ${k}` : cat
    })
    return {
      header: 'Removing from memory…',
      headerTitle: 'Removing from memory…',
      formattedArgs: lines.length > 0 ? lines.join('\n') : null,
    }
  }

  // ── recall: conversational header, filter as args ──────────────────
  if (name === 'recall') {
    const category = str(parsed, 'category')
    const key = str(parsed, 'key')
    const filter = [category, key].filter(Boolean).join(': ')
    return {
      header: 'Checking memory…',
      headerTitle: 'Checking memory…',
      formattedArgs: filter || null,
    }
  }

  // ── bg: action-based header, hide raw JSON ────────
  if (name === 'bg') {
    const action = str(parsed, 'action')?.toLowerCase()
    const pid = parsed['pid'] != null ? String(parsed['pid']) : null
    let header: ReactNode
    let headerTitle: string
    switch (action) {
      case 'list':
        header = 'Listing background processes…'
        headerTitle = 'Listing background processes…'
        break
      case 'status':
        if (pid) {
          header = <>Checking process <Arg>{pid}</Arg>…</>
          headerTitle = `Checking process ${pid}…`
        } else {
          header = 'Checking process status…'
          headerTitle = 'Checking process status…'
        }
        break
      case 'output':
        if (pid) {
          header = <>Reading output of process <Arg>{pid}</Arg>…</>
          headerTitle = `Reading output of process ${pid}…`
        } else {
          header = 'Reading process output…'
          headerTitle = 'Reading process output…'
        }
        break
      case 'stop':
        if (pid) {
          header = <>Stopping process <Arg>{pid}</Arg>…</>
          headerTitle = `Stopping process ${pid}…`
        } else {
          header = 'Stopping process…'
          headerTitle = 'Stopping process…'
        }
        break
      default:
        if (action) {
          header = <>bg: <Arg>{action}</Arg></>
          headerTitle = `bg: ${action}`
        } else {
          header = 'Managing background process…'
          headerTitle = 'Managing background process…'
        }
    }
    return { header, headerTitle, formattedArgs: null }
  }

  // ── skill: conversational header, hide raw args ─────────────
  if (name === 'skill') {
    const skillName = str(parsed, 'skill_name')
    return {
      header: skillName ? <>Loading skill: <Arg>{skillName}</Arg></> : 'Loading skill…',
      headerTitle: skillName ? `Loading skill: ${skillName}` : 'Loading skill…',
      formattedArgs: null,
    }
  }

  // ── write: file name in header, content as args ───────────────────
  if (name === 'write') {
    const path = str(parsed, 'path')
    const fileName = path ? path.split('/').pop() ?? path : null
    const content = str(parsed, 'content')
    return {
      header: fileName ? <>Writing <Arg>{fileName}</Arg></> : 'Writing file…',
      headerTitle: fileName ? `Writing ${fileName}` : 'Writing file…',
      formattedArgs: content,
    }
  }

  // ── read: file name (+ optional range) in header, hide args ────────
  if (name === 'read') {
    const path = str(parsed, 'path')
    const fileName = path ? path.split('/').pop() ?? path : null
    const offset = parsed['offset'] != null && parsed['offset'] !== 0 ? Number(parsed['offset']) : null
    const limit = parsed['limit'] != null ? Number(parsed['limit']) : null
    let rangeLabel = ''
    if (offset !== null || limit !== null) {
      const start = offset ?? 0
      const end = limit !== null ? start + limit : ''
      rangeLabel = ` [${start}:${end}]`
    }
    return {
      header: fileName ? <>Reading <Arg>{fileName}{rangeLabel}</Arg></> : 'Reading file…',
      headerTitle: fileName ? `Reading ${fileName}${rangeLabel}` : 'Reading file…',
      formattedArgs: null,
    }
  }

  // ── edit: file name in header, args as-is ─────────────────────────
  if (name === 'edit') {
    const path = str(parsed, 'path')
    const fileName = path ? path.split('/').pop() ?? path : null
    return {
      header: fileName ? <>Editing <Arg>{fileName}</Arg></> : 'Editing file…',
      headerTitle: fileName ? `Editing ${fileName}` : 'Editing file…',
      formattedArgs: JSON.stringify(parsed, null, 2),
    }
  }

  // ── rm: file name in header, hide args ────────────────────────────
  if (name === 'rm') {
    const path = str(parsed, 'path')
    const fileName = path ? path.split('/').pop() ?? path : null
    return {
      header: fileName ? <>Removing <Arg>{fileName}</Arg></> : 'Removing file…',
      headerTitle: fileName ? `Removing ${fileName}` : 'Removing file…',
      formattedArgs: null,
    }
  }

  // ── ls: directory path in header, hide args ───────────────────────
  // Default path is "." (workspace root) — elide that in the header
  // rather than saying "Listing ." which is noise.
  if (name === 'ls') {
    const path = str(parsed, 'path')
    const isRoot = !path || path === '.' || path === './'
    if (isRoot) {
      return { header: 'Listing workspace', headerTitle: 'Listing workspace', formattedArgs: null }
    }
    const truncated = trunc(path)
    return {
      header: <>Listing <Arg>{truncated}</Arg></>,
      headerTitle: `Listing ${truncated}`,
      formattedArgs: null,
    }
  }

  // ── glob: pattern in header, directory/match as secondary args ─────
  // Pattern is the hero; show directory & non-default match mode only
  // when they add information beyond the defaults.
  if (name === 'glob') {
    const pattern = str(parsed, 'pattern')
    const directory = str(parsed, 'directory')
    const match = str(parsed, 'match')
    const hasScope = directory && directory !== '.' && directory !== './'
    const scope = hasScope ? ` in ${directory}` : ''
    const modeSuffix = match === 'name' ? ' (by name)' : ''
    const lines: string[] = []
    if (pattern) lines.push(`pattern: ${pattern}`)
    if (hasScope) lines.push(`directory: ${directory}`)
    if (match === 'name') lines.push('match: name')
    const truncatedPattern = pattern ? trunc(pattern) : null
    return {
      header: truncatedPattern
        ? <>Finding <Arg>{truncatedPattern}</Arg>{scope}{modeSuffix}</>
        : 'Finding files…',
      headerTitle: truncatedPattern
        ? `Finding ${truncatedPattern}${scope}${modeSuffix}`
        : 'Finding files…',
      formattedArgs: lines.length > 0 ? lines.join('\n') : null,
    }
  }

  // ── grep: pattern in header, directory/include as secondary args ───
  if (name === 'grep') {
    const pattern = str(parsed, 'pattern')
    const directory = str(parsed, 'directory')
    const include = str(parsed, 'include')
    const hasScope = directory && directory !== '.' && directory !== './'
    const scope = hasScope ? ` in ${directory}` : ''
    const hasFilter = include && include !== '*'
    const filter = hasFilter ? ` (${include})` : ''
    const lines: string[] = []
    if (pattern) lines.push(`pattern: ${pattern}`)
    if (hasScope) lines.push(`directory: ${directory}`)
    if (hasFilter) lines.push(`include: ${include}`)
    const truncatedPattern = pattern ? trunc(pattern) : null
    return {
      header: truncatedPattern
        ? <>Searching <Arg>{truncatedPattern}</Arg>{scope}{filter}</>
        : 'Searching files…',
      headerTitle: truncatedPattern
        ? `Searching ${truncatedPattern}${scope}${filter}`
        : 'Searching files…',
      formattedArgs: lines.length > 0 ? lines.join('\n') : null,
    }
  }

  // ── generate_image: filename in header, prompt as args, hide result ──
  // Result is the markdown ``![alt](file.png)`` which the assistant already
  // includes in its reply — rendering it again in the tool panel is noise.
  if (name === 'generate_image') {
    const prompt = str(parsed, 'prompt')
    const rawFilename = str(parsed, 'filename')
    // Strip any trailing extension to match backend sanitiser (which always saves as .png).
    const filename = rawFilename ? `${rawFilename.replace(/\.[^.]+$/, '')}.png` : null
    // Edit-mode inputs: list the source filenames above the prompt so the
    // user can tell the agent is editing vs. generating from scratch.
    const images = Array.isArray(parsed.images)
      ? (parsed.images as unknown[]).map(String).filter((s) => s.length > 0)
      : []
    const argsBody = images.length > 0
      ? `images: ${images.join(', ')}\n\n${prompt}`
      : prompt
    return {
      header: filename
        ? <>Painting <Arg>{filename}</Arg></>
        : 'Painting an image…',
      headerTitle: filename ? `Painting ${filename}` : 'Painting an image…',
      formattedArgs: argsBody,
      suppressResult: true,
    }
  }

  // ── generate_video: filename in header, prompt + inputs as args, hide result ──
  // Mirrors generate_image — the final ``![alt](clip.mp4)`` markdown is already
  // rendered inline by the assistant reply via MarkdownVideo, so repeating it
  // in the tool result accordion would just duplicate the player.
  if (name === 'generate_video') {
    const prompt = str(parsed, 'prompt')
    const rawFilename = str(parsed, 'filename')
    // Backend always writes .mp4 today; show the sanitised name for parity
    // with generate_image so the user sees the final on-disk filename.
    const filename = rawFilename ? `${rawFilename.replace(/\.[^.]+$/, '')}.mp4` : null
    const firstFrames = Array.isArray(parsed.images)
      ? (parsed.images as unknown[]).map(String).filter((s) => s.length > 0)
      : []
    const lastFrame = str(parsed, 'last_frame')
    const references = Array.isArray(parsed.reference_images)
      ? (parsed.reference_images as unknown[]).map(String).filter((s) => s.length > 0)
      : []
    const inputLines: string[] = []
    if (firstFrames.length > 0) inputLines.push(`first_frame: ${firstFrames.join(', ')}`)
    if (lastFrame) inputLines.push(`last_frame: ${lastFrame}`)
    if (references.length > 0) inputLines.push(`references: ${references.join(', ')}`)
    const argsBody = inputLines.length > 0
      ? `${inputLines.join('\n')}\n\n${prompt}`
      : prompt
    return {
      header: filename
        ? <>Filming <Arg>{filename}</Arg></>
        : 'Filming a video…',
      headerTitle: filename ? `Filming ${filename}` : 'Filming a video…',
      formattedArgs: argsBody,
      suppressResult: true,
    }
  }

  // ── team_message: recipients as header, message body as args ─────────
  if (name === 'team_message') {
    const to = Array.isArray(parsed.to) ? (parsed.to as unknown[]).map(String) : []
    const content = str(parsed, 'content')
    const recipientLabel = to.length > 0 ? to.join(', ') : 'team'
    const truncated = trunc(recipientLabel)
    return {
      header: <>Messaging <Arg>{truncated}</Arg></>,
      headerTitle: `Messaging ${truncated}`,
      formattedArgs: content,
    }
  }

  // ── Default: tool name as header, pretty-printed JSON as args ──────
  // Hide args entirely if the object is empty.
  if (Object.keys(parsed).length === 0) {
    return { header: null, headerTitle: null, formattedArgs: null }
  }
  return { header: null, headerTitle: null, formattedArgs: JSON.stringify(parsed, null, 2) }
}
