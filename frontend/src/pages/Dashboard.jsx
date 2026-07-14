import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { listScans } from '../lib/scans'
import { openPortal } from '../lib/billing'

function riskClass(risk) {
  const r = (risk || '').toLowerCase()
  if (r === 'high' || r === 'critical') return 'risk-high'
  if (r === 'medium' || r === 'moderate') return 'risk-med'
  return 'risk-low'
}

function scoreClass(score) {
  if (typeof score !== 'number') return 'risk-low'
  if (score >= 80) return 'risk-low'
  if (score >= 50) return 'risk-med'
  return 'risk-high'
}

export default function Dashboard() {
  const { user, accessToken, plan, isPro, signOut } = useAuth()
  const navigate = useNavigate()
  const [scans, setScans] = useState([])
  const [loading, setLoading] = useState(true)
  const [billingBusy, setBillingBusy] = useState(false)
  const [billingError, setBillingError] = useState('')

  async function manageBilling() {
    setBillingError('')
    try {
      setBillingBusy(true)
      await openPortal(accessToken)
    } catch (err) {
      setBillingError(err.message)
    } finally {
      setBillingBusy(false)
    }
  }

  const load = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setScans(await listScans(user.id))
    setLoading(false)
  }, [user])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="repos-page">
      <div className="ambient-bg" aria-hidden="true"></div>
      <div className="ambient-grid" aria-hidden="true"></div>

      <header className="repos-header">
        <div className="brand-block">
          <Link to="/app" className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7.5 2.5h14v14l-4-4v-6h-6l-4-4Z" fill="#fff" />
              <path d="M2.5 21.5v-9.6l4.4-4.4v9.6h9.6l-4.4 4.4H2.5Z" fill="#fff" fillOpacity="0.82" />
            </svg>
          </Link>
          <div>
            <p className="eyeline">Your workspace</p>
            <h1>Dashboard</h1>
          </div>
        </div>
        <div className="repos-header-actions">
          <span className={`plan-badge${isPro ? ' pro' : ''}`}>{isPro ? (plan === 'team' ? 'Team' : 'Pro') : 'Free'}</span>
          {isPro ? (
            <button type="button" className="secondary-button" onClick={manageBilling} disabled={billingBusy}>
              {billingBusy ? 'Opening…' : 'Manage subscription'}
            </button>
          ) : (
            <a className="secondary-button" href="/#pricing">Upgrade</a>
          )}
          <Link className="secondary-button" to="/repos">My repos</Link>
          <Link className="secondary-button" to="/app">Scanner</Link>
          <button type="button" className="secondary-button" onClick={signOut}>Sign out</button>
        </div>
      </header>

      <main className="repos-main">
        {billingError ? <p className="error-banner">{billingError}</p> : null}
        <section className="panel-card">
          <div className="section-head compact-head">
            <div>
              <p className="section-label">Scan history</p>
              <h3>Your recent repository scans</h3>
            </div>
            <button type="button" className="secondary-button" onClick={load} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>

          {loading ? (
            <p className="empty-state">Loading your scans…</p>
          ) : scans.length === 0 ? (
            <p className="empty-state">
              No scans yet. <Link to="/repos">Pick a repository</Link> and run your first scan.
            </p>
          ) : (
            <ul className="repo-grid">
              {scans.map((s) => (
                <li key={s.id} className="repo-row">
                  <div className="repo-row-main">
                    <span className="repo-row-name">{s.repo_name || s.repo_url}</span>
                    <span className="repo-row-meta">
                      {s.risk_level ? <span className={riskClass(s.risk_level)}>{s.risk_level} risk</span> : null}
                      <span>{s.findings_count} findings</span>
                      <span>{new Date(s.created_at).toLocaleDateString()}</span>
                    </span>
                  </div>
                  <div className="dash-row-actions">
                    {typeof s.score === 'number' ? (
                      <span className={`score-pill ${scoreClass(s.score)}`}>{s.score}</span>
                    ) : null}
                    <button
                      type="button"
                      className="primary-button repo-scan-btn"
                      onClick={() => navigate(`/app?repo=${encodeURIComponent(s.repo_url)}`)}
                    >
                      Re-scan
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  )
}
