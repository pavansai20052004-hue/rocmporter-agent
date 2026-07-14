import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Repos() {
  const { providerToken, signInWithGitHub, signOut, user } = useAuth()
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
            <p className="eyeline">Your GitHub</p>
            <h1>Choose a repository to scan</h1>
          </div>
        </div>
        <div className="repos-header-actions">
          <Link className="secondary-button" to="/app">Open scanner</Link>
          <button type="button" className="secondary-button" onClick={signOut}>Sign out</button>
        </div>
      </header>

      <main className="repos-main">
        {!providerToken ? (
          <section className="panel-card repos-connect">
            <p className="section-label">Connect GitHub</p>
            <h2>Connect your GitHub account</h2>
            <p className="panel-copy">
              {user
                ? 'You are signed in, but we need GitHub access to list your repositories. Connect GitHub to continue.'
                : 'Sign in with GitHub to see and scan all your repositories.'}
            </p>
            <button type="button" className="primary-button" onClick={signInWithGitHub}>
              Connect GitHub
            </button>
          </section>
        ) : (
          <section className="panel-card">
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
      </main>
    </div>
  )
}
