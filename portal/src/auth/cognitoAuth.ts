/**
 * Cognito Hosted UI login via OAuth2 Authorization Code + PKCE (no client secret — this is a
 * public SPA client). Tokens are kept in sessionStorage (cleared when the tab closes) rather
 * than localStorage to limit exposure if an XSS vulnerability is ever introduced.
 */

const DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN as string
const REGION = import.meta.env.VITE_COGNITO_REGION as string
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID as string
const REDIRECT_URI = window.location.origin

const ISSUER_BASE = `https://${DOMAIN}.auth.${REGION}.amazoncognito.com`
const SESSION_KEY = 'daf.portal.tokens'
const VERIFIER_KEY = 'daf.portal.pkce_verifier'

interface StoredTokens {
  idToken: string
  accessToken: string
  refreshToken: string
  expiresAt: number
}

function base64UrlEncode(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

async function sha256(value: string): Promise<ArrayBuffer> {
  return crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
}

function randomString(length: number): string {
  const bytes = new Uint8Array(length)
  crypto.getRandomValues(bytes)
  return base64UrlEncode(bytes.buffer)
}

function readTokens(): StoredTokens | null {
  const raw = sessionStorage.getItem(SESSION_KEY)
  return raw ? (JSON.parse(raw) as StoredTokens) : null
}

function writeTokens(tokens: StoredTokens): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(tokens))
}

/** Redirects the browser to the Cognito Hosted UI login page. */
export async function login(): Promise<void> {
  const verifier = randomString(32)
  sessionStorage.setItem(VERIFIER_KEY, verifier)
  const challenge = base64UrlEncode(await sha256(verifier))

  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: 'code',
    scope: 'openid email profile',
    redirect_uri: REDIRECT_URI,
    code_challenge_method: 'S256',
    code_challenge: challenge,
  })
  window.location.assign(`${ISSUER_BASE}/oauth2/authorize?${params.toString()}`)
}

export function logout(): void {
  sessionStorage.removeItem(SESSION_KEY)
  const params = new URLSearchParams({ client_id: CLIENT_ID, logout_uri: REDIRECT_URI })
  window.location.assign(`${ISSUER_BASE}/logout?${params.toString()}`)
}

/** If the current URL is a Hosted UI redirect (?code=...), exchanges the code for tokens. */
export async function handleRedirectCallback(): Promise<void> {
  const url = new URL(window.location.href)
  const code = url.searchParams.get('code')
  if (!code) return

  const verifier = sessionStorage.getItem(VERIFIER_KEY)
  if (!verifier) return

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: CLIENT_ID,
    code,
    redirect_uri: REDIRECT_URI,
    code_verifier: verifier,
  })

  const response = await fetch(`${ISSUER_BASE}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
  if (!response.ok) {
    throw new Error(`Token exchange failed: ${response.status}`)
  }
  const data = (await response.json()) as {
    id_token: string
    access_token: string
    refresh_token: string
    expires_in: number
  }
  writeTokens({
    idToken: data.id_token,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: Date.now() + data.expires_in * 1000,
  })
  sessionStorage.removeItem(VERIFIER_KEY)
  url.searchParams.delete('code')
  url.searchParams.delete('state')
  window.history.replaceState({}, '', url.toString())
}

async function refresh(tokens: StoredTokens): Promise<StoredTokens | null> {
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: CLIENT_ID,
    refresh_token: tokens.refreshToken,
  })
  const response = await fetch(`${ISSUER_BASE}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
  if (!response.ok) return null
  const data = (await response.json()) as { id_token: string; access_token: string; expires_in: number }
  const updated: StoredTokens = {
    ...tokens,
    idToken: data.id_token,
    accessToken: data.access_token,
    expiresAt: Date.now() + data.expires_in * 1000,
  }
  writeTokens(updated)
  return updated
}

export function isAuthenticated(): boolean {
  return readTokens() !== null
}

/** Returns a valid ID token, refreshing it first if it's expired. Returns null if not logged in. */
export async function getAuthToken(): Promise<string | null> {
  let tokens = readTokens()
  if (!tokens) return null
  if (Date.now() >= tokens.expiresAt - 30_000) {
    tokens = await refresh(tokens)
    if (!tokens) return null
  }
  return tokens.idToken
}
