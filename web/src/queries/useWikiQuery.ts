import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getWikiTree,
  getWikiFile,
  putWikiFile,
  deleteWikiFile,
  getDreamConfig,
  putDreamConfig,
  triggerDreamRun,
} from '@/api/client'
import { queryKeys } from './keys'

export function useWikiTreeQuery(unprocessedOnly = false) {
  return useQuery({
    queryKey: [...queryKeys.wiki.tree(), { unprocessedOnly }],
    queryFn: () => getWikiTree(unprocessedOnly),
  })
}

export function useWikiFileQuery(path: string | null) {
  return useQuery({
    queryKey: queryKeys.wiki.file(path ?? ''),
    queryFn: () => getWikiFile(path as string),
    enabled: !!path,
  })
}

export function useWriteWikiFileMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      putWikiFile(path, content),
    onSuccess: (_data, { path }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.wiki.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.wiki.file(path) })
    },
  })
}

export function useDeleteWikiFileMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => deleteWikiFile(path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.wiki.all() })
    },
  })
}

// ── Dream ────────────────────────────────────────────────────────────────────

export function useDreamConfigQuery() {
  return useQuery({
    queryKey: queryKeys.dream.config(),
    queryFn: getDreamConfig,
  })
}

export function useUpdateDreamConfigMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content: string) => putDreamConfig(content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.dream.config() })
    },
  })
}

export function useTriggerDreamMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: triggerDreamRun,
    onSuccess: () => {
      // Wiki notes list changes after dream runs
      queryClient.invalidateQueries({ queryKey: queryKeys.wiki.all() })
    },
  })
}
