/**
 * TanStack Query hook for the per-session workspace file listing.
 *
 * Mirrors the pattern in ``useMemoryQuery`` — the list is invalidated by the
 * team store whenever a write/edit/rm tool targets the agent workspace so the
 * panel reflects changes as soon as a turn finishes producing them.
 */
import { useQuery } from '@tanstack/react-query'
import { listWorkspaceFiles } from '@/api/client'
import { queryKeys } from './keys'

export function useWorkspaceFilesQuery(sessionId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.team.files(sessionId ?? ''),
    queryFn: () => listWorkspaceFiles(sessionId as string),
    enabled: !!sessionId,
    // Short stale time — the panel is visible only on demand and we also
    // invalidate explicitly from the team store, so a small window is fine.
    staleTime: 5_000,
  })
}
