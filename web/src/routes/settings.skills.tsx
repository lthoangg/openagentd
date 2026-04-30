/**
 * /settings/skills — right-pane empty state. The middle column lives in
 * `SettingsLayout` (`CategoryList`).
 */
import { Sparkles } from 'lucide-react'

import { DetailEmptyState } from '@/components/settings/DetailEmptyState'

export function SkillsListPage() {
  return (
    <DetailEmptyState
      icon={Sparkles}
      title="Select a skill"
      body="Skills are reusable instruction modules agents load on demand via the skill tool."
      ctaTo="/settings/skills/new"
      ctaLabel="New skill"
      tips={[
        'Skills can include scripts, references, and templates.',
        'Reference a skill from an agent\u2019s frontmatter to make it available.',
      ]}
    />
  )
}
