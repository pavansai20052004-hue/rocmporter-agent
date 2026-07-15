import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { listScans } from '../lib/scans'
import { openPortal } from '../lib/billing'
import { useCountUp, useReveal } from '../hooks/useFx'

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

function StatCard({ label, value, suffix, tone }) {
  const ref = useCountUp(value)
  return (
    <div className={`stat-card glow-card${tone ? ' ' + tone : ''}`}>
      <span className="stat-value">
        <span ref={ref}>0</span>
        {suffix ? <em>{suffix}</em> : null}
      </span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

export default function Dashboard() {
  const { user, accessToken, plan, isPro, signOut } = useAuth()
  const navigate = useNavigate()
  const [scans, setScans] = useState([])
  const [loading, setLoading] = useState(true)
  const [billingBusy, setBillingBusy] = useState(false)
  const [billingError, setBillingError] = useState('')
  const revealStats = useReveal()

  const meta = user?.user_metadata || {}
  const displayName = meta.full_name || meta.name || meta.user_name || (user?.email || '').split('@')[0] || 'there'
  const avatar = meta.avatar_url || meta.picture || null

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

  const stats = useMemo(() => {
    const total = scans.length
    const scored = scans.filter((s) => typeof s.score === 'number')
    const avg = scored.length ? Math.round(scored.reduce((a, s) => a + s.score, 0) / scored.length) : 0
    const repos = new Set(scans.map((s) => s.repo_url)).size
    const highRisk = scans.filter((s) => typeof s.score === 'number' && s.score < 50).length
    return { total, avg, repos, highRisk }
  }, [scans])

  return (
    <div className="repos-page dash-page">
      <div className="ambient-bg" aria-hidden="true"></div>
      <div className="ambient-grid" aria-hidden="true"></div>
      <div className="aurora" aria-hidden="true"></div>

      <header className="repos-header">
        <div className="brand-block">
          {avatar ? (
            <img className="dash-avatar" src={avatar} alt="" referrerPolicy="no-referrer" />
          ) : (
            <Link to="/app" className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M7.5 2.5h14v14l-4-4v-6h-6l-4-4Z" fill="#fff" />
                <path d="M2.5 21.5v-9.6l4.4-4.4v9.6h9.6l-4.4 4.4H2.5Z" fill="#fff" fillOpacity="0.82" />
              </svg>
            </Link>
          )}
          <div>
            <p className="eyeline">Welcome back</p>
            <h1>{displayName}</h1>
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

        <div ref={revealStats} className="fx-reveal dash-stats">
          <StatCard label="Total scans" value={stats.total} />
          <StatCard label="Avg readiness" value={stats.avg} suffix="/100" tone="tone-teal" />
          <StatCard label="Repos scanned" value={stats.repos} tone="tone-warm" />
          <StatCard label="High-risk repos" value={stats.highRisk} tone="tone-red" />
        </div>

        <section className="panel-card glow-card dash-history">
          <div className="section-head compact-head">
            <div>
              <p className="section-label">Scan history</p>
              <h3>Your recent repository scans</h3>
            </div>
            <div className="dash-history-actions">
              <Link className="primary-button repo-scan-btn" to="/repos">New scan</Link>
              <button type="button" className="secondary-button" onClick={load} disabled={loading}>
                {loading ? 'Loading…' : 'Refresh'}
              </button>
            </div>
          </div>

          {loading ? (
            <p className="empty-state">Loading your scans…</p>
          ) : scans.length === 0 ? (
            <div className="dash-empty">
              <div className="dash-empty-icon" aria-hidden="true">◇</div>
              <h4>No scans yet</h4>
              <p>Pick a repository and run your first ROCm readiness scan.</p>
              <Link className="primary-button" to="/repos">Choose a repository →</Link>
            </div>
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
                      className="secondary-button repo-scan-btn"
                      onClick={() => navigate(`/app?saved=${s.id}`)}
                    >
                      View report
                    </button>
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
