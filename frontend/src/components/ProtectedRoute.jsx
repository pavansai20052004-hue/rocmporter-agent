import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Guards a route behind authentication. Before Supabase is configured, auth is
// dormant and the route stays open so the scanner keeps working as a tool.
export default function ProtectedRoute({ children }) {
  const { user, loading, isConfigured } = useAuth()

  if (!isConfigured) return children
  if (loading) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" aria-hidden="true"></div>
        <p>Loading your session…</p>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return children
}
