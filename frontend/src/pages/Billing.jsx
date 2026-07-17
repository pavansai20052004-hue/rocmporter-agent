import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { supabase } from '../lib/supabase'
import { getBillingConfig, openPortal, startCheckout } from '../lib/billing'

function formatAmount(payment) {
  if (typeof payment.amount !== 'number') return '—'
  const value = payment.amount / 100
  return payment.currency === 'INR' ? `₹${value.toLocaleString('en-IN')}` : `$${value.toLocaleString()}`
}

export default function Billing() {
  const { user, accessToken, plan, isPro, refreshProfile } = useAuth()
  const [config, setConfig] = useState({ provider: 'stripe' })
  const [proUntil, setProUntil] = useState(null)
  const [payments, setPayments] = useState([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    getBillingConfig().then(setConfig)
    if (!supabase || !user) return
    const { data: profile } = await supabase.from('profiles').select('pro_until').eq('id', user.id).maybeSingle()
    setProUntil(profile?.pro_until ?? null)
    const { data: rows } = await supabase
      .from('payments')
      .select('id,provider,amount,currency,payment_ref,status,created_at')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(24)
    setPayments(rows ?? [])
  }, [user])

  useEffect(() => {
    load()
  }, [load])

  async function upgrade() {
    setError('')
    setNotice('')
    try {
      setBusy('upgrade')
      const result = await startCheckout('pro', accessToken, user)
      if (result?.plan === 'pro') {
        setNotice('Payment successful — welcome to Pro! 🎉')
        await refreshProfile()
        await load()
      }
    } catch (err) {
      if (err.message !== 'Payment cancelled.') setError(err.message)
    } finally {
      setBusy('')
    }
  }

  async function manage() {
    setError('')
    try {
      setBusy('manage')
      await openPortal(accessToken)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const priceLabel = config.provider === 'razorpay' ? (config.priceLabel ?? '₹2,499/month') : '$29/month'

  return (
    <AppShell eyebrow="Payments" title="Billing">
      {notice ? <p className="billing-notice">{notice}</p> : null}
      {error ? <p className="error-banner">{error}</p> : null}

      <div className="billing-grid">
        <section className={`panel-card glow-card billing-plan-card${isPro ? ' pro' : ''}`}>
          <p className="section-label">Current plan</p>
          <div className="billing-plan-row">
            <span className="billing-plan-name">{isPro ? (plan === 'team' ? 'Team' : 'Pro') : 'Free'}</span>
            <span className={`plan-badge${isPro ? ' pro' : ''}`}>{isPro ? 'active' : 'forever free'}</span>
          </div>
          {isPro && proUntil ? (
            <p className="panel-copy">
              Pro access until <strong>{new Date(proUntil).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })}</strong>.
              Renew any time — days stack on top.
            </p>
          ) : isPro ? (
            <p className="panel-copy">Active subscription — thank you for supporting ROCmPorter.</p>
          ) : (
            <p className="panel-copy">
              Free covers unlimited public-repo scans and full reports. Pro unlocks AI patches, one-click
              migration PRs, and private repositories.
            </p>
          )}
          <div className="billing-plan-actions">
            <button type="button" className="primary-button shine-btn" onClick={upgrade} disabled={busy === 'upgrade'}>
              {busy === 'upgrade' ? 'Opening checkout…' : isPro ? `Extend Pro — ${priceLabel}` : `Upgrade to Pro — ${priceLabel}`}
            </button>
            {isPro && config.provider === 'stripe' ? (
              <button type="button" className="secondary-button" onClick={manage} disabled={busy === 'manage'}>
                {busy === 'manage' ? 'Opening…' : 'Manage subscription'}
              </button>
            ) : null}
          </div>
          <p className="billing-provider-note">
            Payments secured by {config.provider === 'razorpay' ? 'Razorpay (UPI, cards, netbanking)' : 'Stripe'}.
            We never see or store your card details.
          </p>
        </section>

        <section className="panel-card glow-card">
          <p className="section-label">What Pro unlocks</p>
          <ul className="price-features billing-features">
            <li>AI-generated single-file ROCm patches</li>
            <li>One-click full-repo migration PRs</li>
            <li>Verify + safe apply / rollback</li>
            <li>GitHub PR review artifacts</li>
            <li>Private repository scanning</li>
          </ul>
        </section>
      </div>

      <section className="panel-card glow-card billing-history">
        <div className="section-head compact-head">
          <div>
            <p className="section-label">Payment history</p>
            <h3>Your receipts</h3>
          </div>
          <button type="button" className="secondary-button" onClick={load}>Refresh</button>
        </div>
        {payments.length === 0 ? (
          <p className="empty-state">No payments yet. Your receipts will appear here after your first upgrade.</p>
        ) : (
          <ul className="billing-payments">
            {payments.map((p) => (
              <li key={p.id} className="billing-payment-row">
                <span className={`billing-pay-status ${p.status}`}>{p.status}</span>
                <strong>{formatAmount(p)}</strong>
                <span className="billing-pay-provider">{p.provider}</span>
                <code>{p.payment_ref || '—'}</code>
                <time>{new Date(p.created_at).toLocaleDateString()}</time>
              </li>
            ))}
          </ul>
        )}
      </section>
    </AppShell>
  )
}
