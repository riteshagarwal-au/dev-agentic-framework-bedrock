import { useCallback, useEffect, useState } from 'react'
import type { ApiClient } from '../api/client'

export interface HitlApprovalViewProps {
  apiClient: ApiClient
  runId: string
}

interface ArtifactRef {
  location?: string
  [key: string]: unknown
}

interface PendingGateTicket {
  ticketId: string
  gateType: string
  context?: {
    summary?: string
    artifactRefs?: ArtifactRef[]
  }
}

function isPendingGateTicketArray(value: unknown): value is PendingGateTicket[] {
  return Array.isArray(value)
}

export function HitlApprovalView({ apiClient, runId }: HitlApprovalViewProps) {
  const [tickets, setTickets] = useState<PendingGateTicket[]>([])
  const [approverName, setApproverName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await apiClient.listPendingGates(runId)
      setTickets(isPendingGateTicketArray(response) ? response : [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch pending gates')
    }
  }, [apiClient, runId])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function handleDecision(ticketId: string, decision: 'APPROVED' | 'REJECTED') {
    try {
      await apiClient.decideGate(ticketId, decision, approverName)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit decision')
    }
  }

  return (
    <div className="hitl-approval-view">
      <h2>Pending approvals</h2>
      <label htmlFor="approverName">Approver</label>
      <input
        id="approverName"
        type="text"
        value={approverName}
        onChange={(event) => setApproverName(event.target.value)}
      />
      {error && <p role="alert">{error}</p>}
      <ul>
        {tickets.map((ticket) => (
          <li key={ticket.ticketId}>
            <p>Gate type: {ticket.gateType}</p>
            {ticket.context?.summary && <p>{ticket.context.summary}</p>}
            <button type="button" onClick={() => handleDecision(ticket.ticketId, 'APPROVED')}>
              Approve
            </button>
            <button type="button" onClick={() => handleDecision(ticket.ticketId, 'REJECTED')}>
              Reject
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
