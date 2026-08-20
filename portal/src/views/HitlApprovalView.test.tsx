import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ApiClient } from '../api/client'
import { HitlApprovalView } from './HitlApprovalView'

const ticket1 = {
  ticketId: 'ticket-1',
  gateType: 'INFRA_APPLY',
  context: { summary: 'Apply terraform plan', artifactRefs: [] },
}
const ticket2 = {
  ticketId: 'ticket-2',
  gateType: 'PR_MERGE',
  context: { summary: 'Merge PR #42', artifactRefs: [] },
}

function fakeApiClient(): ApiClient {
  return {
    startRun: vi.fn(),
    getRunStatus: vi.fn(),
    listPendingGates: vi
      .fn()
      .mockResolvedValueOnce([ticket1, ticket2])
      .mockResolvedValue([ticket2]),
    decideGate: vi.fn().mockResolvedValue({}),
  } as unknown as ApiClient
}

describe('HitlApprovalView', () => {
  it('renders pending tickets, approves, and refreshes the list', async () => {
    const apiClient = fakeApiClient()
    render(<HitlApprovalView apiClient={apiClient} runId="run-1" />)

    expect(await screen.findByText(/Apply terraform plan/)).toBeInTheDocument()
    expect(screen.getByText(/Merge PR #42/)).toBeInTheDocument()

    const approveButtons = screen.getAllByRole('button', { name: /approve/i })
    fireEvent.click(approveButtons[0])

    expect(apiClient.decideGate).toHaveBeenCalledWith('ticket-1', 'APPROVED', '')
    await vi.waitFor(() => expect(apiClient.listPendingGates).toHaveBeenCalledTimes(2))
    expect(await screen.findByText(/Merge PR #42/)).toBeInTheDocument()
    expect(screen.queryByText(/Apply terraform plan/)).not.toBeInTheDocument()
  })

  it('rejects a ticket via decideGate', async () => {
    const apiClient = fakeApiClient()
    render(<HitlApprovalView apiClient={apiClient} runId="run-1" />)

    await screen.findByText(/Apply terraform plan/)
    const rejectButtons = screen.getAllByRole('button', { name: /reject/i })
    fireEvent.click(rejectButtons[0])

    expect(apiClient.decideGate).toHaveBeenCalledWith('ticket-1', 'REJECTED', '')
  })
})
