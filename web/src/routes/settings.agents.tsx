/**
 * /settings/agents — right-pane empty state.
 *
 * The middle column (agent list + search) is rendered by `SettingsLayout`
 * via `CategoryList`. This route only owns the right pane: a friendly
 * placeholder when no agent is selected.
 */
import { Wrench } from 'lucide-react'

import { DetailEmptyState } from '@/components/settings/DetailEmptyState'

export function AgentsListPage() {
  return (
    <DetailEmptyState
      icon={Wrench}
      title="Select an agent"
      body="Pick an agent from the list, or create a new one to define a model, tools, skills, and a system prompt."
      ctaTo="/settings/agents/new"
      ctaLabel="New agent"
      tips={[
        'Lead agents coordinate the team; workers run focused tasks.',
        'Tools and skills are referenced by name from the agent\u2019s frontmatter.',
      ]}
    />
  )
}
