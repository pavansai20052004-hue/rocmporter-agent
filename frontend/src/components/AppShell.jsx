import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const NAV = [
  { to: '/dashboard', label: 'Overview', icon: 'M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z' },
  { to: '/app', label: 'Scanner', icon: 'M12 2a10 10 0 1 0 10 10h-3a7 7 0 1 1-7-7V2Zm0 5a5 5 0 1 0 5 5h-3a2 2 0 1 1-2-2V7Z' },
  { to: '/repos', label: 'My repos', icon: 'M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm2 4h8M8 11h8M8 15h5' },
  { to: '/billing', label: 'Billing', icon: 'M3 7h18v10H3V7Zm0 3h18M6 14h4' },
  { to: '/settings', label: 'Settings', icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.3 7.3 0 0 0-2-1.2l-.4-2.6H9.5l-.4 2.6a7.3 7.3 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.3 7.3 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.3 7.3 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.06-.4.1-.8.1-1.2Z' },
]

export default function AppShell({ eyebrow, title, actions, children, wide = false, overlay = null }) {
  const { user, plan, isPro, signOut } = useAuth()
  const meta = user?.user_metadata || {}
  const avatar = meta.avatar_url || meta.picture || null
  const name = meta.full_name || meta.name || meta.user_name || (user?.email || '').split('@')[0] || 'Account'

  return (
    <div className="shell">
      <div className="ambient-bg" aria-hidden="true"></div>
      <div className="ambient-grid" aria-hidden="true"></div>
      <div className="aurora" aria-hidden="true"></div>
      {overlay}

      <aside className="shell-side">
        <Link to="/" className="shell-brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7.5 2.5h14v14l-4-4v-6h-6l-4-4Z" fill="#fff" />
              <path d="M2.5 21.5v-9.6l4.4-4.4v9.6h9.6l-4.4 4.4H2.5Z" fill="#fff" fillOpacity="0.82" />
            </svg>
          </span>
          <strong>ROCmPorter</strong>
        </Link>

        <nav className="shell-nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `shell-link${isActive ? ' active' : ''}`}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d={item.icon} />
              </svg>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="shell-user">
          {avatar ? (
            <img className="user-avatar" src={avatar} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className="user-avatar user-avatar-fallback">{name.charAt(0).toUpperCase()}</span>
          )}
          <div className="shell-user-meta">
            <span className="shell-user-name" title={name}>{name}</span>
            <span className={`plan-badge${isPro ? ' pro' : ''}`}>{isPro ? (plan === 'team' ? 'Team' : 'Pro') : 'Free'}</span>
          </div>
          <button type="button" className="topbar-linkbtn" onClick={signOut} title="Sign out">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
            </svg>
          </button>
        </div>
      </aside>

      <div className={`shell-main${wide ? ' shell-wide' : ''}`}>
        <header className="shell-head">
          <div>
            {eyebrow ? <p className="eyeline">{eyebrow}</p> : null}
            <h1>{title}</h1>
          </div>
          {actions ? <div className="shell-actions">{actions}</div> : null}
        </header>
        <main className="shell-content">{children}</main>
      </div>
    </div>
  )
}
