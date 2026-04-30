import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'

export function SchedulerPage() {
  const navigate = useNavigate()
  useEffect(() => { navigate({ to: '/cockpit', replace: true }) }, [navigate])
  return null
}
