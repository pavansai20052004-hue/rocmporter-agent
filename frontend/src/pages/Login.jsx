import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { signInWithGoogle, signInWithGitHub, user, isConfigured } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (user) navigate('/app', { replace: true })
  }, [user, navigate])

  return (
    <div className="auth-page">
      <div className="ambient-bg" aria-hidden="true"></div>
      <div className="ambient-grid" aria-hidden="true"></div>

      <div className="auth-card">
        <Link to="/" className="auth-brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7.5 2.5h14v14l-4-4v-6h-6l-4-4Z" fill="#fff" />
              <path d="M2.5 21.5v-9.6l4.4-4.4v9.6h9.6l-4.4 4.4H2.5Z" fill="#fff" fillOpacity="0.82" />
            </svg>
          </span>
          <span>ROCmPorter</span>
        </Link>

        <h1>Welcome back</h1>
        <p className="auth-sub">Sign in to scan your repositories and generate ROCm patches.</p>

        {!isConfigured ? (
          <div className="warning-banner low auth-config-note">
            <strong>Auth not configured yet</strong>
            <span>
              Add your Supabase keys (VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY) to enable sign-in.
              The scanner still works without an account.
            </span>
          </div>
        ) : null}

        <div className="auth-actions">
          <button type="button" className="oauth-button google" onClick={signInWithGoogle} disabled={!isConfigured}>
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
              <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z" />
            </svg>
            Continue with Google
          </button>

          <button type="button" className="oauth-button github" onClick={signInWithGitHub} disabled={!isConfigured}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <path d="M12 1.5A10.5 10.5 0 0 0 8.68 22c.53.1.72-.23.72-.5v-1.75c-2.92.64-3.54-1.25-3.54-1.25-.48-1.22-1.17-1.55-1.17-1.55-.96-.65.07-.64.07-.64 1.06.08 1.62 1.09 1.62 1.09.94 1.61 2.47 1.15 3.07.88.1-.68.37-1.15.67-1.42-2.33-.27-4.78-1.17-4.78-5.19 0-1.15.41-2.08 1.09-2.82-.11-.27-.47-1.34.1-2.79 0 0 .88-.28 2.88 1.07a10 10 0 0 1 5.24 0c2-1.35 2.88-1.07 2.88-1.07.57 1.45.21 2.52.1 2.79.68.74 1.09 1.67 1.09 2.82 0 4.03-2.46 4.92-4.8 5.18.38.33.71.97.71 1.96v2.9c0 .28.19.61.73.5A10.5 10.5 0 0 0 12 1.5Z" />
            </svg>
            Continue with GitHub
          </button>
        </div>

        <p className="auth-fineprint">
          By continuing you agree to our terms. New here? Signing in creates your account automatically.
        </p>

        <Link to="/" className="auth-back">← Back to home</Link>
      </div>
    </div>
  )
}
