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
  const { user, plan, isPro, signOut } = useAuth()
  const navigate = useNavigate()
  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const meta = user?.user_metadata || {}
  const avatar = meta.avatar_url || meta.picture || null
  const name = meta.full_name || meta.name || meta.user_name || (user?.email || '').split('@')[0] || 'Account'
  const providers = user?.app_metadata?.providers || (user?.app_metadata?.provider ? [user.app_metadata.provider] : [])
  const joined = user?.created_at ? new Date(user.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) : '—'

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
      <section className="panel-card glow-card settings-profile">
        <p className="section-label">Profile</p>
        <div className="settings-identity">
          {avatar ? (
            <img className="settings-avatar" src={avatar} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className="settings-avatar user-avatar-fallback">{name.charAt(0).toUpperCase()}</span>
          )}
          <div>
            <h3>{name}</h3>
            <p className="settings-email">{user?.email}</p>
          </div>
          <span className={`plan-badge${isPro ? ' pro' : ''}`}>{isPro ? (plan === 'team' ? 'Team' : 'Pro') : 'Free'}</span>
        </div>

        <dl className="settings-facts">
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

        <p className="settings-note">
          Your name and avatar come from your GitHub/Google account. Update them there and re-sign-in to refresh.
        </p>
      </section>

      <section className="panel-card settings-danger">
        <p className="section-label danger-label">Danger zone</p>
        <h3>Delete account</h3>
        <p className="panel-copy">
          Permanently delete your account, scan history, and payment records. This cannot be undone. Any active
          Pro access is forfeited.
        </p>
        {error ? <p className="error-banner">{error}</p> : null}
        <div className="settings-delete-row">
          <input
            type="text"
            className="repos-search settings-confirm-input"
            placeholder="Type DELETE to confirm"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            aria-label="Type DELETE to confirm account deletion"
          />
          <button
            type="button"
            className="danger-button"
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
