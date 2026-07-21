import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'

/* GitHub's own language colours, so the dots read as familiar rather than decorative. */
const LANG_COLOR = {
  Cuda: '#3A4E3A',
  'C++': '#f34b7d',
  C: '#555555',
  Python: '#3572A5',
  Cython: '#fedf5b',
  Rust: '#dea584',
  Go: '#00ADD8',
  JavaScript: '#f1e05a',
  TypeScript: '#3178c6',
  Julia: '#a270ba',
  Shell: '#89e051',
  CMake: '#DA3434',
  Fortran: '#4d41b1',
}

const CUDA_HINT = /\b(cuda|gpu|nvidia|cudnn|cublas|tensorrt|nccl|kernel|hpc|torch|triton)\b/i
const GPU_LANGS = new Set(['Cuda', 'C++', 'C', 'Cython', 'Fortran'])

/**
 * Ranks how likely a repository is to contain CUDA worth migrating.
 * This turns the page from "all 300 of your repos" into a prioritised worklist —
 * the only reason someone opens this screen is to find the GPU code.
 */
function cudaLikelihood(repo) {
  const haystack = `${repo.name} ${repo.description || ''} ${(repo.topics || []).join(' ')}`
  if (repo.language === 'Cuda') return { tier: 'high', label: 'CUDA' }
  if (CUDA_HINT.test(haystack)) return { tier: 'high', label: 'Likely CUDA' }
  if (GPU_LANGS.has(repo.language)) return { tier: 'medium', label: 'Possible' }
  return { tier: 'low', label: '' }
}

function relativeTime(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const day = 86_400_000
  if (diff < day) return 'today'
  if (diff < 2 * day) return 'yesterday'
  if (diff < 30 * day) return `${Math.floor(diff / day)}d ago`
  if (diff < 365 * day) return `${Math.floor(diff / (30 * day))}mo ago`
  return `${Math.floor(diff / (365 * day))}y ago`
}

function RepoSkeleton() {
  // Reserves the real row height so the list does not shift when data lands.
  return (
    <li className="repo-card is-skeleton" aria-hidden="true">
      <div className="rc-main">
        <span className="sk sk-title"></span>
        <span className="sk sk-desc"></span>
        <span className="sk sk-meta"></span>
      </div>
    </li>
  )
}

export default function Repos() {
  const { providerToken, signInWithGitHub, user } = useAuth()
  const navigate = useNavigate()
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('cuda')

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

  const ranked = useMemo(
    () => repos.map((r) => ({ ...r, likelihood: cudaLikelihood(r) })),
    [repos],
  )

  const counts = useMemo(
    () => ({
      all: ranked.length,
      cuda: ranked.filter((r) => r.likelihood.tier !== 'low').length,
      private: ranked.filter((r) => r.private).length,
    }),
    [ranked],
  )

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const order = { high: 0, medium: 1, low: 2 }
    return ranked
      .filter((r) => {
        if (q && !r.full_name.toLowerCase().includes(q)) return false
        if (filter === 'cuda') return r.likelihood.tier !== 'low'
        if (filter === 'private') return r.private
        return true
      })
      .sort((a, b) => order[a.likelihood.tier] - order[b.likelihood.tier])
  }, [ranked, query, filter])

  // With no GPU-ish repos at all, defaulting to the CUDA filter would show an
  // empty screen — fall back to showing everything.
  useEffect(() => {
    if (!loading && repos.length > 0 && counts.cuda === 0 && filter === 'cuda') setFilter('all')
  }, [loading, repos.length, counts.cuda, filter])

  if (!providerToken) {
    return (
      <AppShell eyebrow="Your GitHub" title="Repositories">
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
      </AppShell>
    )
  }

  return (
    <AppShell
      eyebrow="Your GitHub"
      title="Repositories"
      actions={
        <button type="button" className="secondary-button" onClick={loadRepos} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      }
    >
      <section className="repos-panel">
        <div className="repos-controls">
          <div className="repos-search-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              id="repo-filter"
              type="search"
              placeholder="Filter by name…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="repos-search"
              aria-label="Filter repositories by name"
            />
          </div>

          <div className="repos-tabs" role="tablist" aria-label="Repository filter">
            {[
              { id: 'cuda', label: 'GPU candidates', n: counts.cuda },
              { id: 'all', label: 'All', n: counts.all },
              { id: 'private', label: 'Private', n: counts.private },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={filter === tab.id}
                className={`repos-tab${filter === tab.id ? ' is-active' : ''}`}
                onClick={() => setFilter(tab.id)}
              >
                {tab.label}
                <span className="repos-tab-count">{tab.n}</span>
              </button>
            ))}
          </div>
        </div>

        {error ? <p className="error-banner">{error}</p> : null}

        <ul className="repo-cards">
          {loading && repos.length === 0 ? (
            Array.from({ length: 5 }, (_, i) => <RepoSkeleton key={i} />)
          ) : visible.length === 0 ? (
            <li className="repos-empty">
              <p>{query ? `No repositories match “${query}”.` : 'Nothing to show for this filter.'}</p>
            </li>
          ) : (
            visible.map((repo) => (
              <li key={repo.id} className={`repo-card tier-${repo.likelihood.tier}`}>
                <div className="rc-main">
                  <div className="rc-title">
                    <span className="rc-name">{repo.full_name}</span>
                    {repo.private ? <span className="rc-chip is-private">private</span> : null}
                    {repo.likelihood.label ? (
                      <span className={`rc-chip is-${repo.likelihood.tier}`}>{repo.likelihood.label}</span>
                    ) : null}
                  </div>

                  {repo.description ? <p className="rc-desc">{repo.description}</p> : null}

                  <div className="rc-meta">
                    {repo.language ? (
                      <span className="rc-lang">
                        <i style={{ background: LANG_COLOR[repo.language] || '#8b93a7' }}></i>
                        {repo.language}
                      </span>
                    ) : null}
                    {repo.stargazers_count > 0 ? (
                      <span className="rc-stat">
                        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                          <path d="M12 2l3 6.3 6.9 1-5 4.8 1.2 6.9L12 17.8 5.9 21l1.2-6.9-5-4.8 6.9-1z" />
                        </svg>
                        {repo.stargazers_count.toLocaleString()}
                      </span>
                    ) : null}
                    <span className="rc-stat">{repo.default_branch}</span>
                    <span className="rc-stat rc-time">updated {relativeTime(repo.updated_at)}</span>
                  </div>
                </div>

                <button
                  type="button"
                  className="rc-scan"
                  onClick={() => navigate(`/app?repo=${encodeURIComponent(repo.html_url)}`)}
                >
                  Scan
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                    <path d="M5 12h13M13 6l6 6-6 6" />
                  </svg>
                </button>
              </li>
            ))
          )}
        </ul>
      </section>
    </AppShell>
  )
}
