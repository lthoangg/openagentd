/** TanStack Query hooks for the MCP server CRUD API. */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listMcpServers,
  getMcpServer,
  createMcpServer,
  updateMcpServer,
  deleteMcpServer,
  restartMcpServer,
  type ServerBody,
} from '@/api/client'
import { queryKeys } from './keys'

export function useMcpServersQuery() {
  return useQuery({
    queryKey: queryKeys.mcp.list(),
    queryFn: listMcpServers,
    staleTime: 10_000,
  })
}

export function useMcpServerQuery(name: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.mcp.detail(name ?? ''),
    queryFn: () => getMcpServer(name as string),
    enabled: !!name,
  })
}

function invalidateAll(client: ReturnType<typeof useQueryClient>) {
  client.invalidateQueries({ queryKey: queryKeys.mcp.all() })
}

export function useCreateMcpServerMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ name, server }: { name: string; server: ServerBody }) =>
      createMcpServer(name, server),
    onSuccess: () => invalidateAll(client),
  })
}

export function useUpdateMcpServerMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ name, server }: { name: string; server: ServerBody }) =>
      updateMcpServer(name, server),
    onSuccess: (_data, { name }) => {
      invalidateAll(client)
      client.invalidateQueries({ queryKey: queryKeys.mcp.detail(name) })
    },
  })
}

export function useDeleteMcpServerMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => deleteMcpServer(name),
    onSuccess: () => invalidateAll(client),
  })
}

export function useRestartMcpServerMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => restartMcpServer(name),
    onSuccess: (_data, name) => {
      client.invalidateQueries({ queryKey: queryKeys.mcp.detail(name) })
    },
  })
}
