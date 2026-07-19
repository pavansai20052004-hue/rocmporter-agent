import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { listScans } from '../lib/scans'
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
        <span ref={ref}>{value}</span>
        {suffix ? <em>{suffix}</em> : null}
      </span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [scans, setScans] = useState([])
  const [loading, setLoading] = useState(true)
  const revealStats = useReveal()

  const meta = user?.user_metadata || {}
  const displayName = meta.full_name || meta.name || meta.user_name || (user?.email || '').split('@')[0] || 'there'

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
    <AppShell
      eyebrow="Welcome back"
      title={displayName}
      actions={<Link className="primary-button shine-btn shell-cta" to="/repos">New scan</Link>}
    >
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
          <button type="button" className="secondary-button" onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
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
    </AppShell>
  )
}
