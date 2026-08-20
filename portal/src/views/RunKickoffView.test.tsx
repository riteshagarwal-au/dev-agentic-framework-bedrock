import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ApiClient } from '../api/client'
import { RunKickoffView } from './RunKickoffView'

function fakeApiClient(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    startRun: vi.fn().mockResolvedValue({ runId: 'run-abc' }),
    getRunStatus: vi.fn(),
    listPendingGates: vi.fn(),
    decideGate: vi.fn(),
    ...overrides,
  } as unknown as ApiClient
}

describe('RunKickoffView', () => {
  it('submits the form and renders the returned runId', async () => {
    const apiClient = fakeApiClient()
    render(<RunKickoffView apiClient={apiClient} />)

    fireEvent.change(screen.getByLabelText(/target app/i), { target: { value: 'my-synthetic-app' } })
    fireEvent.change(screen.getByLabelText(/target repo/i), { target: { value: 'my-org/my-app-repo' } })
    fireEvent.click(screen.getByRole('button', { name: /start run/i }))

    expect(apiClient.startRun).toHaveBeenCalledWith(
      expect.objectContaining({ targetApp: 'my-synthetic-app', targetRepo: 'my-org/my-app-repo' }),
    )
    expect(await screen.findByText(/run-abc/)).toBeInTheDocument()
  })

  it('shows an error message on failure', async () => {
    const apiClient = fakeApiClient({ startRun: vi.fn().mockRejectedValue(new Error('boom')) })
    render(<RunKickoffView apiClient={apiClient} />)

    fireEvent.change(screen.getByLabelText(/target app/i), { target: { value: 'my-app' } })
    fireEvent.change(screen.getByLabelText(/target repo/i), { target: { value: 'my-org/my-app-repo' } })
    fireEvent.click(screen.getByRole('button', { name: /start run/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('boom')
  })
})
