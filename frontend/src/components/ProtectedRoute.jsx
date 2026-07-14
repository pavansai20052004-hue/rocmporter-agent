import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// True while an OAuth provider is redirecting back with a token/code still in
// the URL. We must NOT redirect to /login during this window or the token is
// dropped before Supabase can establish the session.
function hasPendingOAuth() {
  if (typeof window === 'undefined') return false
  const hash = window.location.hash || ''
  const search = window.location.search || ''
  return (
    hash.includes('access_token') ||
    hash.includes('error') ||
    new URLSearchParams(search).has('code')
  )
}

// Guards a route behind authentication. Before Supabase is configured, auth is
// dormant and the route stays open so the scanner keeps working as a tool.
export default function ProtectedRoute({ children }) {
  const { user, loading, isConfigured } = useAuth()

  if (!isConfigured) return children
  if (loading || (!user && hasPendingOAuth())) {
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
