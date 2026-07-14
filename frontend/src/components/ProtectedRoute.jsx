import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Classifies the current URL after an OAuth redirect:
//  'error'   -> the provider returned an error; do NOT wait, send to login
//  'pending' -> a success token/code is present; wait for the session
//  'none'    -> normal navigation
function oauthState() {
  if (typeof window === 'undefined') return 'none'
  const hash = window.location.hash || ''
  const params = new URLSearchParams(window.location.search || '')
  if (hash.includes('error') || params.has('error')) return 'error'
  if (hash.includes('access_token') || params.has('code')) return 'pending'
  return 'none'
}

// Guards a route behind authentication. Before Supabase is configured, auth is
// dormant and the route stays open so the scanner keeps working as a tool.
export default function ProtectedRoute({ children }) {
  const { user, loading, isConfigured } = useAuth()

  if (!isConfigured) return children

  const state = oauthState()
  // Provider returned an error — bounce to login with a flag instead of looping.
  if (!user && state === 'error') return <Navigate to="/login?auth_error=1" replace />

  if (loading || (!user && state === 'pending')) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" aria-hidden="true"></div>
        <p>Signing you in…</p>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return children
}
