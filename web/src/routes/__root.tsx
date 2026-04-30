import { QueryClientProvider } from '@tanstack/react-query'
// Temporarily disabled for clean recordings — re-enable when done.
// import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { Link, Outlet } from '@tanstack/react-router'
import { queryClient } from '@/lib/query-client'
import { Home } from 'lucide-react'
import { ToastStack } from '@/components/ToastStack'
import { SkipLink } from '@/components/motion'

export function Root() {
  // Theme application is handled by `initTheme()` in main.tsx and the
  // inline pre-paint script in index.html. Do not force `.dark` here —
  // it would override the user's preference.
  return (
    <QueryClientProvider client={queryClient}>
      <SkipLink />
      <Outlet />
      <ToastStack />
      {/* <ReactQueryDevtools initialIsOpen={false} /> */}
    </QueryClientProvider>
  )
}

export function NotFound() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-6 bg-(--color-bg)">
      <div className="text-center">
        <p className="font-mono text-6xl font-bold text-(--color-text-muted)">404</p>
        <p className="mt-3 text-sm text-(--color-text-muted)">Page not found</p>
      </div>
      <Link
        to="/"
        className="interactive-weight flex items-center gap-2 rounded-lg bg-(--color-accent-subtle) px-4 py-2 text-sm text-(--color-accent) ring-1 ring-(--color-border-strong) transition-colors hover:bg-(--color-accent-subtle)"
      >
        <Home size={14} />
        Go home
      </Link>
    </div>
  )
}
