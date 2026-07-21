import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { deleteAccount } from '../lib/api'

function providerLabel(id) {
  if (id === 'github') return 'GitHub'
  if (id === 'google') return 'Google'
  return id
}

export default function Settings() {
  const { user, plan, isPro, signOut, providerToken, signInWithGitHub } = useAuth()
  const navigate = useNavigate()
  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const meta = user?.user_metadata || {}
  const avatar = meta.avatar_url || meta.picture || null
  const name = meta.full_name || meta.name || meta.user_name || (user?.email || '').split('@')[0] || 'Account'
  const providers = user?.app_metadata?.providers || (user?.app_metadata?.provider ? [user.app_metadata.provider] : [])
  const joined = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })
    : '—'

  async function handleDelete() {
    if (confirmText !== 'DELETE') return
    setError('')
    try {
      setDeleting(true)
      await deleteAccount()
      await signOut()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'Could not delete your account.')
      setDeleting(false)
    }
  }

  return (
    <AppShell eyebrow="Account" title="Settings">
      {/* ---------- profile ---------- */}
      <section className="set-card">
        <p className="section-label">Profile</p>

        <div className="set-identity">
          {avatar ? (
            <img className="set-avatar" src={avatar} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className="set-avatar is-fallback">{name.charAt(0).toUpperCase()}</span>
          )}
          <div className="set-identity-text">
            <h3>{name}</h3>
            <p>{user?.email}</p>
          </div>
          <span className={`set-plan${isPro ? ' is-pro' : ''}`}>
            {isPro ? (plan === 'team' ? 'Team' : 'Pro') : 'Free'}
          </span>
        </div>

        <dl className="set-facts">
          <div>
            <dt>Signed in with</dt>
            <dd>{providers.length ? providers.map(providerLabel).join(', ') : '—'}</dd>
          </div>
          <div>
            <dt>Member since</dt>
            <dd>{joined}</dd>
          </div>
          <div>
            <dt>Plan</dt>
            <dd>{isPro ? (plan === 'team' ? 'Team' : 'Pro') : 'Free'}</dd>
          </div>
        </dl>

        <p className="set-note">
          Your name and avatar come from your GitHub/Google account. Update them there and sign in again to refresh.
        </p>
      </section>

      {/* ---------- connected accounts ----------
          GitHub OAuth tokens expire regularly, and until now the only signal was
          an error on the Repos page. Surfacing the state here makes reconnecting
          obvious instead of something you have to go discover. */}
      <section className="set-card">
        <p className="section-label">Connected accounts</p>

        <div className={`set-conn${providerToken ? ' is-live' : ''}`}>
          <span className="set-conn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 1.5A10.5 10.5 0 0 0 8.68 22c.53.1.72-.23.72-.5v-1.75c-2.92.64-3.54-1.25-3.54-1.25-.48-1.22-1.17-1.55-1.17-1.55-.96-.65.07-.64.07-.64 1.06.08 1.62 1.09 1.62 1.09.94 1.61 2.47 1.15 3.07.88.1-.68.37-1.15.67-1.42-2.33-.27-4.78-1.17-4.78-5.19 0-1.15.41-2.08 1.09-2.82-.11-.27-.47-1.34.1-2.79 0 0 .88-.28 2.88 1.07a10 10 0 0 1 5.24 0c2-1.35 2.88-1.07 2.88-1.07.57 1.45.21 2.52.1 2.79.68.74 1.09 1.67 1.09 2.82 0 4.03-2.46 4.92-4.8 5.18.38.33.71.97.71 1.96v2.9c0 .28.19.61.73.5A10.5 10.5 0 0 0 12 1.5Z" />
            </svg>
          </span>

          <div className="set-conn-text">
            <span className="set-conn-name">
              GitHub
              <span className={`set-dot${providerToken ? ' is-live' : ''}`} aria-hidden="true"></span>
              <span className="set-conn-state">{providerToken ? 'Connected' : 'Not connected'}</span>
            </span>
            <p>
              {providerToken
                ? 'Repository access is active. You can list and scan your repositories, private ones included.'
                : 'GitHub access has expired or was never granted. Reconnect to list and scan your repositories.'}
            </p>
          </div>

          <button type="button" className="set-conn-btn" onClick={signInWithGitHub}>
            {providerToken ? 'Reconnect' : 'Connect GitHub'}
          </button>
        </div>

        <p className="set-note">
          GitHub access tokens are short-lived by design. If the Repositories page says your authorization expired,
          reconnect here — it takes a few seconds and nothing else about your account changes.
        </p>
      </section>

      {/* ---------- danger zone ---------- */}
      <section className="set-card is-danger">
        <p className="section-label is-danger-label">Danger zone</p>
        <h3 className="set-danger-title">Delete account</h3>
        <p className="set-danger-copy">
          Permanently delete your account, scan history, and payment records. This cannot be undone. Any active Pro
          access is forfeited.
        </p>

        {error ? <p className="error-banner">{error}</p> : null}

        <div className="set-delete-row">
          <input
            type="text"
            className="set-confirm"
            placeholder="Type DELETE to confirm"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            aria-label="Type DELETE to confirm account deletion"
          />
          <button
            type="button"
            className="set-delete-btn"
            disabled={confirmText !== 'DELETE' || deleting}
            onClick={handleDelete}
          >
            {deleting ? 'Deleting…' : 'Delete my account'}
          </button>
        </div>
      </section>
    </AppShell>
  )
}
