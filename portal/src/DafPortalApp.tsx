import { useState } from 'react'
import type { ApiClient } from './api/client'
import { HitlApprovalView } from './views/HitlApprovalView'
import { RunKickoffView } from './views/RunKickoffView'
import { RunStatusView } from './views/RunStatusView'

export interface DafPortalAppProps {
  apiClient: ApiClient
}

type Tab = 'kickoff' | 'status' | 'approval'

/** Not wired into main.tsx yet — see Task 17 report for why App.tsx was left untouched. */
export function DafPortalApp({ apiClient }: DafPortalAppProps) {
  const [tab, setTab] = useState<Tab>('kickoff')
  const [runId, setRunId] = useState('')

  return (
    <div className="daf-portal-app">
      <nav>
        <button type="button" onClick={() => setTab('kickoff')}>
          Kickoff
        </button>
        <button type="button" onClick={() => setTab('status')}>
          Status
        </button>
        <button type="button" onClick={() => setTab('approval')}>
          Approvals
        </button>
      </nav>
      <label htmlFor="runIdInput">Run ID</label>
      <input id="runIdInput" type="text" value={runId} onChange={(event) => setRunId(event.target.value)} />

      {tab === 'kickoff' && <RunKickoffView apiClient={apiClient} />}
      {tab === 'status' && runId && <RunStatusView apiClient={apiClient} runId={runId} />}
      {tab === 'approval' && runId && <HitlApprovalView apiClient={apiClient} runId={runId} />}
    </div>
  )
}
