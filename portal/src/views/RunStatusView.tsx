import { useEffect, useState } from 'react'
import type { ApiClient } from '../api/client'

export interface RunStatusViewProps {
  apiClient: ApiClient
  runId: string
  pollIntervalMs?: number
}

interface TaskGraphNode {
  taskId?: string
  taskType?: string
  agentId?: string
  completed?: boolean
}

interface ArtifactLink {
  taskType?: string
  filename?: string
  downloadUrl?: string
}

interface RunStatusResponse {
  runId?: string
  status?: string
  currentStep?: string
  currentStepIndex?: number
  taskGraph?: TaskGraphNode[]
  artifacts?: ArtifactLink[]
}

function isRunStatusResponse(value: unknown): value is RunStatusResponse {
  return typeof value === 'object' && value !== null
}

export function RunStatusView({ apiClient, runId, pollIntervalMs = 4000 }: RunStatusViewProps) {
  const [status, setStatus] = useState<string | null>(null)
  const [currentStep, setCurrentStep] = useState<string | null>(null)
  const [currentStepIndex, setCurrentStepIndex] = useState<number | null>(null)
  const [taskGraph, setTaskGraph] = useState<TaskGraphNode[]>([])
  const [artifacts, setArtifacts] = useState<ArtifactLink[]>([])
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
          setCurrentStepIndex(response.currentStepIndex ?? null)
          setTaskGraph(response.taskGraph ?? [])
          setArtifacts(response.artifacts ?? [])
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
  const isTerminal = status === 'COMPLETED' || status === 'FAILED' || status === 'HALTED'

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
      {taskGraph.length > 0 && (
        <ol className="task-graph-list">
          {taskGraph.map((node, index) => {
            const isCurrent = !isTerminal && currentStepIndex === index
            const label = node.completed ? 'Done' : isCurrent ? 'In progress' : 'Pending'
            return (
              <li key={node.taskId ?? index} data-state={label.toLowerCase().replace(' ', '-')}>
                <strong>{node.taskType ?? `Step ${index + 1}`}</strong>
                {node.agentId && <span> ({node.agentId})</span>} — {label}
              </li>
            )
          })}
        </ol>
      )}
      {error && <p role="alert">{error}</p>}
      {artifacts.length > 0 && (
        <div className="run-artifacts">
          <h3>Generated artifacts</h3>
          <ul>
            {artifacts.map((artifact, index) => (
              <li key={`${artifact.taskType ?? index}`}>
                <a href={artifact.downloadUrl} target="_blank" rel="noreferrer">
                  {artifact.filename ?? artifact.taskType ?? `artifact-${index}`}
                </a>
                {artifact.taskType && <span> ({artifact.taskType})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
