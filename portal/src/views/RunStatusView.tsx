import { useEffect, useState } from 'react'
import type { ApiClient } from '../api/client'

export interface RunStatusViewProps {
  apiClient: ApiClient
  runId: string
  pollIntervalMs?: number
}

interface RunStatusResponse {
  runId?: string
  status?: string
  currentStep?: string
}

function isRunStatusResponse(value: unknown): value is RunStatusResponse {
  return typeof value === 'object' && value !== null
}

export function RunStatusView({ apiClient, runId, pollIntervalMs = 4000 }: RunStatusViewProps) {
  const [status, setStatus] = useState<string | null>(null)
  const [currentStep, setCurrentStep] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const response = await apiClient.getRunStatus(runId)
        if (cancelled) return
        if (isRunStatusResponse(response)) {
          setStatus(response.status ?? null)
          setCurrentStep(response.currentStep ?? null)
        }
        setError(null)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to fetch run status')
        }
      }
    }

    poll()
    const intervalId = setInterval(poll, pollIntervalMs)
    return () => {
      cancelled = true
      clearInterval(intervalId)
    }
  }, [apiClient, runId, pollIntervalMs])

  const isAwaitingHitl = status === 'AWAITING_HITL'

  return (
    <div className="run-status-view">
      <h2>Run status</h2>
      {isAwaitingHitl && (
        <div role="alert" className="hitl-banner">
          Awaiting human approval
        </div>
      )}
      {status && <p>Status: {status}</p>}
      {currentStep && <p>Current step: {currentStep}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
