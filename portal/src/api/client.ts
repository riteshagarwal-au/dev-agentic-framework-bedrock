/**
 * Cognito-authenticated API client for the DAF portal (Task 17.2).
 *
 * REST paths (must match backend/src/daf/portal_api/handlers.py):
 *   POST /runs                      -> startRun
 *   GET  /runs/{runId}/status       -> getRunStatus
 *   GET  /runs/{runId}/gates        -> listPendingGates
 *   POST /gates/{ticketId}/decide   -> decideGate
 */

export type GetAuthToken = () => Promise<string | null>

export interface StartRunPayload {
  runId: string
  targetApp: string
  sourceEnv: { subscriptionId: string; resourceGroup: string; resourceName: string }
  targetPlatform: string
  targetRepo: string
  budgetCeiling: {
    maxTotalTokens: number
    maxCostUsd: number
    maxWallClockMs: number
    maxSteps: number
    maxOpusInvocations: number
  }
}

export type GateDecision = 'APPROVED' | 'REJECTED'

export class UnauthenticatedError extends Error {
  constructor() {
    super('No auth token available; refusing to issue an unauthenticated request')
    this.name = 'UnauthenticatedError'
  }
}

export interface ApiClientOptions {
  baseUrl: string
  getAuthToken: GetAuthToken
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly getAuthToken: GetAuthToken

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl
    this.getAuthToken = options.getAuthToken
  }

  async startRun(payload: StartRunPayload): Promise<unknown> {
    return this.request('POST', '/runs', payload)
  }

  async getRunStatus(runId: string): Promise<unknown> {
    return this.request('GET', `/runs/${runId}/status`)
  }

  async listPendingGates(runId: string): Promise<unknown> {
    return this.request('GET', `/runs/${runId}/gates`)
  }

  async decideGate(ticketId: string, decision: GateDecision, approver: string): Promise<unknown> {
    return this.request('POST', `/gates/${ticketId}/decide`, { ticketId, decision, approver })
  }

  private async request(method: 'GET' | 'POST', path: string, body?: unknown): Promise<unknown> {
    // Route guard: never issue a network call without a valid token —
    // unauthenticated requests must never reach a run-control action.
    const token = await this.getAuthToken()
    if (!token) {
      throw new UnauthenticatedError()
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })

    const parsed: unknown = await response.json().catch(() => undefined)

    if (!response.ok) {
      const message =
        parsed && typeof parsed === 'object' && 'message' in parsed && typeof (parsed as { message: unknown }).message === 'string'
          ? (parsed as { message: string }).message
          : `Request failed with status ${response.status}`
      throw new Error(message)
    }

    return parsed
  }
}
