import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient, UnauthenticatedError } from './client'

const BASE_URL = 'https://api.example.test'

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: () => Promise.resolve(body) } as Response
}

describe('ApiClient', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  describe('when unauthenticated (getAuthToken resolves null)', () => {
    const getAuthToken = vi.fn().mockResolvedValue(null)

    it('startRun rejects without calling fetch', async () => {
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })
      await expect(
        client.startRun({
          runId: 'run-1',
          targetApp: 'app-1',
          sourceEnv: { subscriptionId: 'sub', resourceGroup: 'rg', resourceName: 'app-1-rg' },
          targetPlatform: 'ECS_FARGATE',
          targetRepo: 'my-org/my-app-repo',
          budgetCeiling: {
            maxTotalTokens: 1,
            maxCostUsd: 1,
            maxWallClockMs: 1,
            maxSteps: 1,
            maxOpusInvocations: 1,
          },
        }),
      ).rejects.toThrow(UnauthenticatedError)
      expect(fetch).not.toHaveBeenCalled()
    })

    it('getRunStatus rejects without calling fetch', async () => {
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })
      await expect(client.getRunStatus('run-1')).rejects.toThrow(UnauthenticatedError)
      expect(fetch).not.toHaveBeenCalled()
    })

    it('listPendingGates rejects without calling fetch', async () => {
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })
      await expect(client.listPendingGates('run-1')).rejects.toThrow(UnauthenticatedError)
      expect(fetch).not.toHaveBeenCalled()
    })

    it('decideGate rejects without calling fetch', async () => {
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })
      await expect(client.decideGate('ticket-1', 'APPROVED', 'user-1')).rejects.toThrow(
        UnauthenticatedError,
      )
      expect(fetch).not.toHaveBeenCalled()
    })
  })

  describe('when authenticated (getAuthToken resolves a token)', () => {
    const getAuthToken = vi.fn().mockResolvedValue('token-abc')

    it('startRun calls fetch with POST /runs and Authorization header', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({ runId: 'run-1', status: 'RUNNING' }))
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })
      const payload = {
        runId: 'run-1',
        targetApp: 'app-1',
        sourceEnv: { subscriptionId: 'sub', resourceGroup: 'rg', resourceName: 'app-1-rg' },
        targetPlatform: 'ECS_FARGATE',
        targetRepo: 'my-org/my-app-repo',
        budgetCeiling: {
          maxTotalTokens: 1,
          maxCostUsd: 1,
          maxWallClockMs: 1,
          maxSteps: 1,
          maxOpusInvocations: 1,
        },
      }

      await client.startRun(payload)

      expect(fetch).toHaveBeenCalledWith(
        `${BASE_URL}/runs`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer token-abc' }),
          body: JSON.stringify(payload),
        }),
      )
    })

    it('getRunStatus calls fetch with GET /runs/{runId}/status and Authorization header', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: 'RUNNING' }))
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })

      await client.getRunStatus('run-1')

      expect(fetch).toHaveBeenCalledWith(
        `${BASE_URL}/runs/run-1/status`,
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({ Authorization: 'Bearer token-abc' }),
        }),
      )
    })

    it('listPendingGates calls fetch with GET /runs/{runId}/gates and Authorization header', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse([]))
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })

      await client.listPendingGates('run-1')

      expect(fetch).toHaveBeenCalledWith(
        `${BASE_URL}/runs/run-1/gates`,
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({ Authorization: 'Bearer token-abc' }),
        }),
      )
    })

    it('decideGate calls fetch with POST /gates/{ticketId}/decide and Authorization header', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({ ticketId: 'ticket-1', decision: 'APPROVED' }))
      const client = new ApiClient({ baseUrl: BASE_URL, getAuthToken })

      await client.decideGate('ticket-1', 'APPROVED', 'user-1')

      expect(fetch).toHaveBeenCalledWith(
        `${BASE_URL}/gates/ticket-1/decide`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer token-abc' }),
          body: JSON.stringify({ ticketId: 'ticket-1', decision: 'APPROVED', approver: 'user-1' }),
        }),
      )
    })
  })
})
