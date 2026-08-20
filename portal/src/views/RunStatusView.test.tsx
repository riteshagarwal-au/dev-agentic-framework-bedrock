import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiClient } from '../api/client'
import { RunStatusView } from './RunStatusView'

function fakeApiClient(status: string): ApiClient {
  return {
    startRun: vi.fn(),
    getRunStatus: vi.fn().mockResolvedValue({ runId: 'run-1', status }),
    listPendingGates: vi.fn(),
    decideGate: vi.fn(),
  } as unknown as ApiClient
}

describe('RunStatusView', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it.each(['PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'HALTED'])(
    'renders the %s status',
    async (status) => {
      const apiClient = fakeApiClient(status)
      render(<RunStatusView apiClient={apiClient} runId="run-1" />)

      expect(await screen.findByText(new RegExp(`Status: ${status}`))).toBeInTheDocument()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    },
  )

  it('shows a distinct banner when status is AWAITING_HITL', async () => {
    const apiClient = fakeApiClient('AWAITING_HITL')
    render(<RunStatusView apiClient={apiClient} runId="run-1" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/awaiting human approval/i)
  })

  it('renders the task graph with per-step progress', async () => {
    const apiClient = {
      startRun: vi.fn(),
      getRunStatus: vi.fn().mockResolvedValue({
        runId: 'run-1',
        status: 'RUNNING',
        currentStepIndex: 1,
        taskGraph: [
          { taskId: 'run-1-0', taskType: 'DISCOVERY_COLLECT', agentId: 'DISCOVERY', completed: true },
          { taskId: 'run-1-1', taskType: 'DISCOVERY_REASON', agentId: 'DISCOVERY', completed: false },
        ],
      }),
      listPendingGates: vi.fn(),
      decideGate: vi.fn(),
    } as unknown as ApiClient

    render(<RunStatusView apiClient={apiClient} runId="run-1" />)

    expect(await screen.findByText(/DISCOVERY_COLLECT/)).toBeInTheDocument()
    expect(screen.getByText(/DISCOVERY_REASON/)).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })
})
