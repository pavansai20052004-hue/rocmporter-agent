import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { startCheckout } from '../lib/billing'
import { useReveal, useTilt } from '../hooks/useFx'

const FEATURES = [
  {
    title: 'Evidence-driven scans',
    body: 'Every finding points at the exact file, line, and code snippet. No hand-waving — proof you can click.',
    icon: 'M4 6h16M4 12h10M4 18h7',
  },
  {
    title: 'AI ROCm patches',
    body: 'Reviewable, single-file migration patches generated on demand — with rationale you can read.',
    icon: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  },
  {
    title: 'Verify before apply',
    body: 'Syntax checks, drift detection, artifact hashes, and diff replay run before anything touches your code.',
    icon: 'M20 6L9 17l-5-5',
  },
  {
    title: 'Safe apply & rollback',
    body: 'Patches apply inside an isolated workspace copy with backup-and-restore rollback. Zero fear.',
    icon: 'M3 12a9 9 0 1 0 9-9M3 12l4-4M3 12l4 4',
  },
  {
    title: 'GitHub-native reviews',
    body: 'Line-aware PR review artifacts with suggested patch text, ready to post to your pull request.',
    icon: 'M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22',
  },
  {
    title: 'Audit-grade exports',
    body: 'Offline HTML, JSON, Markdown, diffs, and checksummed zip bundles for CI and compliance.',
    icon: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  },
]

const STEPS = [
  { n: '01', title: 'Point at a repo', body: 'Paste any GitHub URL — or connect GitHub and pick from all your repositories, private included.' },
  { n: '02', title: 'Get the evidence', body: 'A ROCm readiness score, ranked findings, and the exact lines of CUDA holding you back.' },
  { n: '03', title: 'Ship the migration', body: 'Generate verified patches, export audit bundles, and post GitHub-ready reviews.' },
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

const TERMINAL_LINES = [
  { cls: 'tl-cmd', text: '$ rocmporter scan pytorch/extension-cpp' },
  { cls: 'tl-dim', text: 'cloning… analyzing 111 files' },
  { cls: 'tl-hit', text: '▸ cuda_runtime.h        muladd.cu:6' },
  { cls: 'tl-hit', text: '▸ nvcc build flags      setup.py:43' },
  { cls: 'tl-hit', text: '▸ torch.cuda paths      setup.py:34' },
  { cls: 'tl-ok', text: '✓ readiness 62/100 · patch plan ready' },
]

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M7.5 2.5h14v14l-4-4v-6h-6l-4-4Z" fill="#fff" />
        <path d="M2.5 21.5v-9.6l4.4-4.4v9.6h9.6l-4.4 4.4H2.5Z" fill="#fff" fillOpacity="0.82" />
      </svg>
    </span>
  )
}

function HeroScene() {
  return (
    <div className="hero-scene" aria-hidden="true">
      <div className="scene-orbit">
        <span className="orbit-dot od-1"></span>
        <span className="orbit-dot od-2"></span>
        <span className="orbit-dot od-3"></span>
      </div>

      <div className="chip3d">
        <div className="chip3d-inner">
          <div className="chip-face chip-front">
            <span className="chip-label-top">CUDA</span>
            <div className="chip-die">
              <div className="chip-grid">
                {Array.from({ length: 16 }, (_, i) => (
                  <span key={i} className="chip-cell" style={{ animationDelay: `${(i % 5) * 0.35}s` }}></span>
                ))}
              </div>
            </div>
            <span className="chip-label-bot">ROCm</span>
          </div>
          <div className="chip-face chip-back"></div>
          <div className="chip-face chip-left"></div>
          <div className="chip-face chip-right"></div>
          <div className="chip-face chip-top"></div>
          <div className="chip-face chip-bottom"></div>
        </div>
        <div className="chip-shadow"></div>
      </div>

      <div className="hero-terminal">
        <div className="ht-bar">
          <span></span><span></span><span></span>
          <em>rocmporter</em>
        </div>
        <div className="ht-body">
          {TERMINAL_LINES.map((line, i) => (
            <p key={i} className={`tl ${line.cls}`} style={{ animationDelay: `${0.6 + i * 0.55}s` }}>
              {line.text}
            </p>
          ))}
        </div>
      </div>
    </div>
  )
}

function FeatureCard({ feature, index }) {
  const tilt = useTilt(8)
  const reveal = useReveal()
  return (
    <div ref={reveal} className="fx-reveal" style={{ transitionDelay: `${(index % 3) * 90}ms` }}>
      <article ref={tilt} className="feature-card fx-tilt glow-card">
        <span className="feature-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={feature.icon} />
          </svg>
        </span>
        <h3>{feature.title}</h3>
        <p>{feature.body}</p>
      </article>
    </div>
  )
}

export default function Landing() {
  const { user, accessToken, signOut } = useAuth()
  const navigate = useNavigate()
  const [checkoutError, setCheckoutError] = useState('')
  const [busyPlan, setBusyPlan] = useState('')

  const revealSteps = useReveal()
  const revealPricing = useReveal()
  const revealCta = useReveal()

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
    <div className="landing landing-v2">
      <div className="ambient-bg" aria-hidden="true"></div>
      <div className="ambient-grid" aria-hidden="true"></div>
      <div className="aurora" aria-hidden="true"></div>

      <header className="landing-nav glass-nav">
        <div className="brand-block">
          <BrandMark />
          <strong>ROCmPorter</strong>
        </div>
        <nav className="landing-nav-links">
          <a href="#how">How it works</a>
          <a href="#features">Features</a>
          <a href="#pricing">Pricing</a>
          {user ? (
            <>
              <Link className="secondary-button nav-btn" to="/dashboard">Dashboard</Link>
              <button type="button" className="secondary-button nav-btn" onClick={signOut}>Sign out</button>
            </>
          ) : (
            <Link className="primary-button nav-btn shine-btn" to="/login">Sign in</Link>
          )}
        </nav>
      </header>

      <section className="landing-hero hero-v2">
        <div className="hero-copy">
          <span className="hero-eyebrow pulse-chip">
            <span className="live-dot"></span> CUDA → AMD ROCm, automated
          </span>
          <h1>
            Break free from <span className="grad-text">CUDA lock-in</span>.
            <br />
            Ship on AMD in <span className="grad-text-alt">minutes</span>.
          </h1>
          <p className="hero-sub">
            ROCmPorter scans any GitHub repository, pinpoints every NVIDIA dependency with line-level evidence,
            and generates verified ROCm migration patches you can trust.
          </p>
          <div className="hero-actions">
            <Link className="primary-button hero-cta shine-btn" to={user ? '/app' : '/login'}>
              {user ? 'Open the scanner' : 'Scan your first repo — free'}
            </Link>
            <a className="secondary-button hero-cta ghost-cta" href="#how">
              See how it works ↓
            </a>
          </div>
          <div className="hero-proof">
            <span><strong>Line-level</strong> evidence</span>
            <span className="proof-sep"></span>
            <span><strong>Verified</strong> patches</span>
            <span className="proof-sep"></span>
            <span><strong>1-click</strong> GitHub reviews</span>
          </div>
        </div>
        <HeroScene />
      </section>

      <section id="how" className="how-section">
        <div ref={revealSteps} className="fx-reveal">
          <p className="section-label center-label">How it works</p>
          <h2 className="section-title">Three steps from CUDA to ROCm</h2>
          <div className="steps-grid">
            {STEPS.map((step, i) => (
              <div key={step.n} className="step-card glow-card" style={{ animationDelay: `${i * 120}ms` }}>
                <span className="step-num grad-text">{step.n}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
                {i < STEPS.length - 1 ? <span className="step-connector" aria-hidden="true"></span> : null}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="landing-features features-v2">
        <p className="section-label center-label">Features</p>
        <h2 className="section-title">Everything you need to actually ship</h2>
        <div className="features-grid-v2">
          {FEATURES.map((f, i) => (
            <FeatureCard key={f.title} feature={f} index={i} />
          ))}
        </div>
      </section>

      <section id="pricing" className="pricing">
        <div ref={revealPricing} className="fx-reveal">
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
              <article key={tier.plan} className={`price-card glow-card${tier.highlighted ? ' featured' : ''}`}>
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
                  className={tier.highlighted ? 'primary-button price-cta shine-btn' : 'secondary-button price-cta'}
                  onClick={() => handlePlan(tier)}
                  disabled={busyPlan === tier.plan}
                >
                  {busyPlan === tier.plan ? 'Redirecting…' : tier.cta}
                </button>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="cta-band" ref={revealCta}>
        <div className="cta-band-inner fx-reveal glow-card">
          <h2>
            Your CUDA code is <span className="grad-text">one scan away</span> from AMD.
          </h2>
          <p>Free for public repositories. No credit card required.</p>
          <Link className="primary-button hero-cta shine-btn" to={user ? '/app' : '/login'}>
            Start scanning now →
          </Link>
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
