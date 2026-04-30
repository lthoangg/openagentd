/**
 * /settings/mcp — right-pane empty state. The middle column lives in
 * `SettingsLayout` (`CategoryList`).
 */
import { Plug } from 'lucide-react'

import { DetailEmptyState } from '@/components/settings/DetailEmptyState'

export function McpListPage() {
  return (
    <DetailEmptyState
      icon={Plug}
      title="Select an MCP server"
      body="MCP servers expose tools and resources to your agents over stdio or HTTP."
      ctaTo="/settings/mcp/new"
      ctaLabel="New MCP server"
      tips={[
        'Stdio servers run locally as a child process; HTTP servers are remote.',
        'Use restart from the detail view if a server fails to start.',
      ]}
    />
  )
}
