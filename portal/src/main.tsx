import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { DafPortalApp } from './DafPortalApp.tsx'
import { ApiClient } from './api/client'
import { getAuthToken, handleRedirectCallback, isAuthenticated, login } from './auth/cognitoAuth'

async function bootstrap() {
  await handleRedirectCallback()
  if (!isAuthenticated()) {
    await login()
    return
  }

  const apiClient = new ApiClient({
    baseUrl: import.meta.env.VITE_API_BASE_URL as string,
    getAuthToken,
  })

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <DafPortalApp apiClient={apiClient} />
    </StrictMode>,
  )
}

bootstrap()
