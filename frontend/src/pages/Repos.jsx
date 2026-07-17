import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'

export default function Repos() {
  const { providerToken, signInWithGitHub, user } = useAuth()
  const navigate = useNavigate()
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')

  const loadRepos = useCallback(async () => {
    if (!providerToken) return
    setLoading(true)
    setError('')
    try {
      const all = []
      // GitHub paginates at 100/page; pull up to 3 pages (300 repos).
      for (let page = 1; page <= 3; page += 1) {
        const res = await fetch(
          `https://api.github.com/user/repos?per_page=100&sort=updated&page=${page}`,
          { headers: { Authorization: `Bearer ${providerToken}`, Accept: 'application/vnd.github+json' } },
        )
        if (!res.ok) {
          if (res.status === 401) {
            setError('Your GitHub authorization expired. Reconnect GitHub to refresh access.')
            return
          }
          throw new Error(`GitHub API returned ${res.status}`)
        }
        const batch = await res.json()
        all.push(...batch)
        if (batch.length < 100) break
      }
      setRepos(all)
    } catch (err) {
      setError(err.message || 'Could not load your repositories.')
    } finally {
      setLoading(false)
    }
  }, [providerToken])

  useEffect(() => {
    loadRepos()
  }, [loadRepos])

  const filtered = repos.filter((r) => r.full_name.toLowerCase().includes(query.toLowerCase()))

  return (
    <AppShell eyebrow="Your GitHub" title="Repositories">
      {!providerToken ? (
        <section className="panel-card glow-card repos-connect">
          <p className="section-label">Connect GitHub</p>
          <h2>Connect your GitHub account</h2>
          <p className="panel-copy">
            {user
              ? 'You are signed in, but we need GitHub access to list your repositories. Connect GitHub to continue.'
              : 'Sign in with GitHub to see and scan all your repositories.'}
          </p>
          <button type="button" className="primary-button shine-btn" onClick={signInWithGitHub}>
            Connect GitHub
          </button>
        </section>
      ) : (
        <section className="panel-card glow-card">
          <div className="repos-toolbar">
            <input
              type="search"
              placeholder="Filter repositories…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="repos-search"
            />
            <button type="button" className="secondary-button" onClick={loadRepos} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>

          {error ? <p className="error-banner">{error}</p> : null}

          {loading && repos.length === 0 ? (
            <p className="empty-state">Loading your repositories…</p>
          ) : filtered.length === 0 ? (
            <p className="empty-state">No repositories match “{query}”.</p>
          ) : (
            <ul className="repo-grid">
              {filtered.map((repo) => (
                <li key={repo.id} className="repo-row">
                  <div className="repo-row-main">
                    <span className="repo-row-name">
                      {repo.full_name}
                      {repo.private ? <span className="repo-badge">private</span> : null}
                    </span>
                    {repo.description ? <span className="repo-row-desc">{repo.description}</span> : null}
                    <span className="repo-row-meta">
                      {repo.language ? <span>{repo.language}</span> : null}
                      <span>★ {repo.stargazers_count}</span>
                      <span>{repo.default_branch}</span>
                    </span>
                  </div>
                  <button
                    type="button"
                    className="primary-button repo-scan-btn"
                    onClick={() => navigate(`/app?repo=${encodeURIComponent(repo.html_url)}`)}
                  >
                    Scan
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </AppShell>
  )
}
