import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { listScans } from '../lib/scans'
import { useCountUp, useReveal } from '../hooks/useFx'

const ICONS = {
  scans: 'M3 3v18h18M7 15l3-4 3 3 4-6',
  readiness: 'M12 2a10 10 0 1 0 10 10h-10z',
  repos: 'M4 5a2 2 0 0 1 2-2h12v18H6a2 2 0 0 1-2-2zM8 3v18',
  risk: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
}

function riskClass(risk) {
  const r = (risk || '').toLowerCase()
  if (r === 'high' || r === 'critical') return 'risk-high'
  if (r === 'medium' || r === 'moderate') return 'risk-med'
  return 'risk-low'
}
function scoreTone(score) {
  if (typeof score !== 'number') return 'tone-none'
  if (score >= 70) return 'tone-good'
  if (score >= 45) return 'tone-mid'
  return 'tone-bad'
}

function StatCard({ label, value, suffix, tone, icon, context }) {
  const ref = useCountUp(value)
  return (
    <div className={`stat-tile${tone ? ' ' + tone : ''}`}>
      <span className="st-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <path d={icon} />
        </svg>
      </span>
      <span className="st-value">
        {/* Rendered value is the source of truth; the count-up only animates it. */}
        <span ref={ref}>{value}</span>
        {suffix ? <em>{suffix}</em> : null}
      </span>
      <span className="st-label">{label}</span>
      {context ? <span className="st-context">{context}</span> : null}
    </div>
  )
}

/** Distribution of readiness scores — turns a list of numbers into a shape you can read. */
function ReadinessBar({ scans }) {
  const buckets = useMemo(() => {
    const scored = scans.filter((s) => typeof s.score === 'number')
    const b = { bad: 0, mid: 0, good: 0 }
    scored.forEach((s) => {
      if (s.score >= 70) b.good += 1
      else if (s.score >= 45) b.mid += 1
      else b.bad += 1
    })
    return { ...b, total: scored.length }
  }, [scans])

  if (!buckets.total) return null
  const pct = (n) => (n / buckets.total) * 100

  return (
    <section className="readiness-panel">
      <div className="rd-head">
        <p className="section-label">Portfolio readiness</p>
        <span className="rd-total">{buckets.total} scored</span>
      </div>
      <div className="rd-bar" role="img" aria-label={`${buckets.bad} high risk, ${buckets.mid} moderate, ${buckets.good} close to ready`}>
        {buckets.bad > 0 ? <span className="rd-seg is-bad" style={{ width: `${pct(buckets.bad)}%` }}></span> : null}
        {buckets.mid > 0 ? <span className="rd-seg is-mid" style={{ width: `${pct(buckets.mid)}%` }}></span> : null}
        {buckets.good > 0 ? <span className="rd-seg is-good" style={{ width: `${pct(buckets.good)}%` }}></span> : null}
      </div>
      <ul className="rd-legend">
        <li><i className="is-bad"></i>Heavy CUDA lock-in<strong>{buckets.bad}</strong></li>
        <li><i className="is-mid"></i>Moderate<strong>{buckets.mid}</strong></li>
        <li><i className="is-good"></i>Close to ready<strong>{buckets.good}</strong></li>
      </ul>
    </section>
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
    // Without a user there is nothing to fetch — clear the loading state anyway,
    // otherwise the skeleton rows render forever instead of the empty state.
    if (!user) {
      setScans([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      setScans(await listScans(user.id))
    } finally {
      setLoading(false)
    }
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
      <div ref={revealStats} className="fx-reveal stat-grid">
        <StatCard label="Total scans" value={stats.total} icon={ICONS.scans} context={stats.total ? 'across all repositories' : 'run your first scan'} />
        <StatCard label="Avg readiness" value={stats.avg} suffix="/100" tone="tone-teal" icon={ICONS.readiness} context={stats.avg ? (stats.avg >= 60 ? 'portfolio in good shape' : 'migration work ahead') : 'no scores yet'} />
        <StatCard label="Repos scanned" value={stats.repos} tone="tone-warm" icon={ICONS.repos} context="unique repositories" />
        <StatCard label="High-risk repos" value={stats.highRisk} tone="tone-red" icon={ICONS.risk} context={stats.highRisk ? 'below 50/100' : 'none flagged'} />
      </div>

      <ReadinessBar scans={scans} />

      <section className="history-panel">
        <div className="hp-head">
          <div>
            <p className="section-label">Scan history</p>
            <h3>Your recent repository scans</h3>
          </div>
          <button type="button" className="secondary-button" onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>

        {loading ? (
          <ul className="scan-list">
            {Array.from({ length: 3 }, (_, i) => (
              <li key={i} className="scan-row is-skeleton" aria-hidden="true">
                <span className="sk sk-title"></span>
                <span className="sk sk-meta"></span>
              </li>
            ))}
          </ul>
        ) : scans.length === 0 ? (
          <div className="scan-empty">
            <span className="se-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-4.3-4.3" />
              </svg>
            </span>
            <h4>No scans yet</h4>
            <p>Pick a repository and run your first ROCm readiness scan.</p>
            <Link className="primary-button" to="/repos">Choose a repository</Link>
          </div>
        ) : (
          <ul className="scan-list">
            {scans.map((s) => (
              <li key={s.id} className="scan-row">
                <span className={`sr-score ${scoreTone(s.score)}`}>
                  {typeof s.score === 'number' ? s.score : '—'}
                </span>

                <div className="sr-main">
                  <span className="sr-name">{s.repo_name || s.repo_url}</span>
                  <span className="sr-meta">
                    {s.risk_level ? <span className={riskClass(s.risk_level)}>{s.risk_level} risk</span> : null}
                    <span>{s.findings_count} findings</span>
                    <span>{new Date(s.created_at).toLocaleDateString()}</span>
                  </span>
                </div>

                <div className="sr-actions">
                  <button type="button" className="sr-btn" onClick={() => navigate(`/app?saved=${s.id}`)}>
                    View report
                  </button>
                  <button type="button" className="sr-btn is-primary" onClick={() => navigate(`/app?repo=${encodeURIComponent(s.repo_url)}`)}>
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
