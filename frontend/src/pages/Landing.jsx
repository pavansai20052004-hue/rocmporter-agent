import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { startCheckout } from '../lib/billing'

const FEATURES = [
  {
    title: 'Evidence-driven scans',
    body: 'Point at any GitHub repo. We clone it and flag every CUDA / NVIDIA assumption with the exact file and line.',
    icon: 'M4 6h16M4 12h10M4 18h7',
  },
  {
    title: 'AI ROCm patches',
    body: 'Generate reviewable, single-file ROCm migration patches — with verification and safe apply / rollback.',
    icon: 'M12 2l2.4 7.4H22l-6 4.6 2.3 7.4L12 17l-6.3 4.4L8 14 2 9.4h7.6L12 2z',
  },
  {
    title: 'Ship with confidence',
    body: 'GitHub-ready PR review artifacts, audit-grade export bundles, and a portability score for every repo.',
    icon: 'M20 6L9 17l-5-5',
  },
]

const PRICING_TIERS = [
  {
    plan: 'free',
    name: 'Free',
    price: '$0',
    cadence: 'forever',
    tagline: 'For trying it on public repos.',
    features: ['Unlimited public repo scans', 'Full ROCm readiness report', 'Migration checklist', 'Offline exports'],
    cta: 'Start free',
    highlighted: false,
  },
  {
    plan: 'pro',
    name: 'Pro',
    price: '$29',
    cadence: 'per month',
    tagline: 'For engineers shipping the migration.',
    features: ['Everything in Free', 'AI single-file ROCm patches', 'Verify + safe apply / rollback', 'GitHub PR review artifacts', 'Private repository scanning'],
    cta: 'Upgrade to Pro',
    highlighted: true,
  },
  {
    plan: 'team',
    name: 'Team',
    price: 'Custom',
    cadence: 'contact us',
    tagline: 'For teams porting many repos.',
    features: ['Everything in Pro', 'CI/CD scan + patch pipelines', 'AMD Developer Cloud validation', 'Shared audit bundles & seats', 'Priority support'],
    cta: 'Talk to us',
    highlighted: false,
  },
]

export default function Landing() {
  const { user, accessToken, signOut } = useAuth()
  const navigate = useNavigate()
  const [checkoutError, setCheckoutError] = useState('')
  const [busyPlan, setBusyPlan] = useState('')

  async function handlePlan(tier) {
    setCheckoutError('')
    if (tier.plan === 'free') {
      navigate(user ? '/app' : '/login')
      return
    }
    if (tier.plan === 'team') {
      window.location.href = 'mailto:sales@rocmporter.app'
      return
    }
    if (!user) {
      navigate('/login')
      return
    }
    try {
      setBusyPlan(tier.plan)
      await startCheckout(tier.plan, accessToken)
    } catch (err) {
      setCheckoutError(err.message)
    } finally {
      setBusyPlan('')
    }
  }

  return (
    <div className="landing">
      <div className="ambient-bg" aria-hidden="true"></div>
      <div className="ambient-grid" aria-hidden="true"></div>

      <header className="landing-nav">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7.5 2.5h14v14l-4-4v-6h-6l-4-4Z" fill="#fff" />
              <path d="M2.5 21.5v-9.6l4.4-4.4v9.6h9.6l-4.4 4.4H2.5Z" fill="#fff" fillOpacity="0.82" />
            </svg>
          </span>
          <strong>ROCmPorter</strong>
        </div>
        <nav className="landing-nav-links">
          <a href="#features">Features</a>
          <a href="#pricing">Pricing</a>
          {user ? (
            <>
              <Link className="secondary-button nav-btn" to="/app">Open app</Link>
              <button type="button" className="secondary-button nav-btn" onClick={signOut}>Sign out</button>
            </>
          ) : (
            <Link className="primary-button nav-btn" to="/login">Sign in</Link>
          )}
        </nav>
      </header>

      <section className="landing-hero">
        <span className="hero-eyebrow">CUDA → AMD ROCm, automated</span>
        <h1>Migrate CUDA code to AMD ROCm in minutes, not months.</h1>
        <p className="hero-sub">
          ROCmPorter scans any GitHub repository for NVIDIA-specific code, scores its ROCm readiness, and generates
          reviewable migration patches — with evidence, verification, and audit-grade exports.
        </p>
        <div className="hero-actions">
          <Link className="primary-button hero-cta" to={user ? '/app' : '/login'}>
            {user ? 'Open the scanner' : 'Start free →'}
          </Link>
          <a className="secondary-button hero-cta" href="#pricing">See pricing</a>
        </div>
        <p className="hero-note">No credit card for public-repo scans. Connect GitHub to scan private repos.</p>
      </section>

      <section id="features" className="landing-features">
        {FEATURES.map((f) => (
          <article key={f.title} className="feature-card">
            <span className="feature-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d={f.icon} />
              </svg>
            </span>
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </article>
        ))}
      </section>

      <section id="pricing" className="pricing">
        <div className="pricing-head">
          <p className="section-label">Pricing</p>
          <h2>Start free. Pay when you ship patches.</h2>
          <p className="pricing-sub">
            Scanning real repositories is always free. Paid plans unlock AI patch generation, verified apply,
            and GitHub review automation.
          </p>
        </div>
        {checkoutError ? <p className="error-banner pricing-error">{checkoutError}</p> : null}
        <div className="pricing-grid">
          {PRICING_TIERS.map((tier) => (
            <article key={tier.plan} className={`price-card${tier.highlighted ? ' featured' : ''}`}>
              {tier.highlighted ? <span className="price-badge">Most popular</span> : null}
              <h3>{tier.name}</h3>
              <div className="price-amount">
                <span className="price-value">{tier.price}</span>
                <span className="price-cadence">{tier.cadence}</span>
              </div>
              <p className="price-tagline">{tier.tagline}</p>
              <ul className="price-features">
                {tier.features.map((feature) => (
                  <li key={feature}>{feature}</li>
                ))}
              </ul>
              <button
                type="button"
                className={tier.highlighted ? 'primary-button price-cta' : 'secondary-button price-cta'}
                onClick={() => handlePlan(tier)}
                disabled={busyPlan === tier.plan}
              >
                {busyPlan === tier.plan ? 'Redirecting…' : tier.cta}
              </button>
            </article>
          ))}
        </div>
      </section>

      <footer className="site-footer">
        <div className="site-footer-brand">
          <strong>ROCmPorter Agent</strong>
          <span>Evidence-driven CUDA → AMD ROCm migration reports and reviewable patches.</span>
        </div>
        <span className="site-footer-note">
          <Link to="/terms">Terms</Link> · <Link to="/privacy">Privacy</Link> · © 2026 ROCmPorter
        </span>
      </footer>
    </div>
  )
}
