/** TanStack Query hooks for the sandbox deny-list settings. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getSandboxSettings,
  updateSandboxSettings,
  type SandboxSettings,
} from '@/api/client'
import { queryKeys } from './keys'

export function useSandboxSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.settings.sandbox(),
    queryFn: getSandboxSettings,
    staleTime: 30_000,
  })
}

export function useUpdateSandboxSettingsMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: SandboxSettings) => updateSandboxSettings(body),
    onSuccess: (data) => {
      client.setQueryData(queryKeys.settings.sandbox(), data)
    },
  })
}
