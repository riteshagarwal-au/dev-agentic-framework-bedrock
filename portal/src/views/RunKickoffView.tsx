import { useState } from 'react'
import type { ApiClient } from '../api/client'

export interface RunKickoffViewProps {
  apiClient: ApiClient
}

interface StartRunResponse {
  runId?: string
}

function isStartRunResponse(value: unknown): value is StartRunResponse {
  return typeof value === 'object' && value !== null
}

export function RunKickoffView({ apiClient }: RunKickoffViewProps) {
  const [targetApp, setTargetApp] = useState('')
  const [targetRepo, setTargetRepo] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setRunId(null)
    setSubmitting(true)
    try {
      const generatedRunId = `run-${Date.now()}`
      const response = await apiClient.startRun({
        runId: generatedRunId,
        targetApp,
        sourceEnv: {
          subscriptionId: `synthetic-${targetApp}`,
          resourceGroup: `rg-${targetApp}`,
          resourceName: targetApp,
        },
        targetPlatform: 'ECS_FARGATE',
        targetRepo,
        budgetCeiling: {
          maxTotalTokens: 1_000_000,
          maxCostUsd: 50.0,
          maxWallClockMs: 3_600_000,
          maxSteps: 20,
          maxOpusInvocations: 3,
        },
      })
      if (!isStartRunResponse(response) || !response.runId) {
        throw new Error('Start run response did not include a runId')
      }
      setRunId(response.runId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="run-kickoff-view">
      <h2>Start a new run</h2>
      <form onSubmit={handleSubmit}>
        <label htmlFor="targetApp">Target app</label>
        <input
          id="targetApp"
          type="text"
          value={targetApp}
          onChange={(event) => setTargetApp(event.target.value)}
          required
        />
        <label htmlFor="targetRepo">Target repo (org/repo)</label>
        <input
          id="targetRepo"
          type="text"
          value={targetRepo}
          onChange={(event) => setTargetRepo(event.target.value)}
          placeholder="my-org/my-app-repo"
          required
        />
        <button type="submit" disabled={submitting}>
          Start run
        </button>
      </form>
      {runId && <p role="status">Run started: {runId}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
