import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { supabase } from '../lib/supabase'
import { getBillingConfig, openPortal, startCheckout } from '../lib/billing'

const PRO_FEATURES = [
  'AI-generated single-file ROCm patches',
  'One-click full-repo migration PRs',
  'Verify + safe apply / rollback',
  'GitHub PR review artifacts',
  'Private repository scanning',
]

const FREE_FEATURES = [
  'Unlimited public-repo scans',
  'Full ROCm readiness reports',
  'Migration checklist',
  'Offline exports',
]

function formatAmount(payment) {
  if (typeof payment.amount !== 'number') return '—'
  const value = payment.amount / 100
  return payment.currency === 'INR' ? `₹${value.toLocaleString('en-IN')}` : `$${value.toLocaleString()}`
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  )
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
        setNotice('Payment successful — welcome to Pro.')
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
  const planName = isPro ? (plan === 'team' ? 'Team' : 'Pro') : 'Free'

  return (
    <AppShell eyebrow="Payments" title="Billing">
      {notice ? <p className="billing-notice">{notice}</p> : null}
      {error ? <p className="error-banner">{error}</p> : null}

      <div className="bill-grid">
        {/* ---------- current plan ---------- */}
        <section className={`bill-plan${isPro ? ' is-pro' : ''}`}>
          <div className="bp-top">
            <div>
              <p className="section-label">Current plan</p>
              <div className="bp-name-row">
                <span className="bp-name">{planName}</span>
                <span className={`bp-badge${isPro ? ' is-pro' : ''}`}>{isPro ? 'active' : 'forever free'}</span>
              </div>
            </div>
            {isPro ? (
              <span className="bp-crest" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2l3 6.3 6.9 1-5 4.8 1.2 6.9L12 17.8 5.9 21l1.2-6.9-5-4.8 6.9-1z" />
                </svg>
              </span>
            ) : null}
          </div>

          {isPro && proUntil ? (
            <p className="bp-copy">
              Pro access until{' '}
              <strong>
                {new Date(proUntil).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })}
              </strong>
              . Renew any time — days stack on top.
            </p>
          ) : isPro ? (
            <p className="bp-copy">Active subscription — thank you for supporting ROCmPorter.</p>
          ) : (
            <p className="bp-copy">
              Free covers unlimited public-repo scans and full reports. Pro unlocks AI patches, one-click
              migration PRs, and private repositories.
            </p>
          )}

          <div className="bp-actions">
            <button type="button" className="bp-cta" onClick={upgrade} disabled={busy === 'upgrade'}>
              {busy === 'upgrade' ? 'Opening checkout…' : isPro ? `Extend Pro — ${priceLabel}` : `Upgrade to Pro — ${priceLabel}`}
            </button>
            {isPro && config.provider === 'stripe' ? (
              <button type="button" className="secondary-button" onClick={manage} disabled={busy === 'manage'}>
                {busy === 'manage' ? 'Opening…' : 'Manage subscription'}
              </button>
            ) : null}
          </div>

          <p className="bp-note">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <rect x="4" y="10" width="16" height="11" rx="2" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" />
            </svg>
            Secured by {config.provider === 'razorpay' ? 'Razorpay — UPI, cards, netbanking' : 'Stripe'}. Card details never
            touch our servers.
          </p>
        </section>

        {/* ---------- plan comparison ---------- */}
        <section className="bill-compare">
          <p className="section-label">What you get</p>
          <div className="bc-cols">
            <div className={`bc-col${!isPro ? ' is-current' : ''}`}>
              <span className="bc-title">Free</span>
              <ul>
                {FREE_FEATURES.map((f) => (
                  <li key={f}>
                    <CheckIcon />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
            <div className={`bc-col is-pro-col${isPro ? ' is-current' : ''}`}>
              <span className="bc-title">
                Pro
                {!isPro ? <em>{priceLabel}</em> : null}
              </span>
              <ul>
                {PRO_FEATURES.map((f) => (
                  <li key={f}>
                    <CheckIcon />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </div>

      {/* ---------- receipts ---------- */}
      <section className="bill-history">
        <div className="hp-head">
          <div>
            <p className="section-label">Payment history</p>
            <h3>Your receipts</h3>
          </div>
          <button type="button" className="secondary-button" onClick={load}>
            Refresh
          </button>
        </div>

        {payments.length === 0 ? (
          <p className="bill-empty">No payments yet. Receipts appear here after your first upgrade.</p>
        ) : (
          <div className="bill-table-wrap">
            <table className="bill-table">
              <thead>
                <tr>
                  <th scope="col">Status</th>
                  <th scope="col">Amount</th>
                  <th scope="col">Provider</th>
                  <th scope="col">Reference</th>
                  <th scope="col">Date</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <span className={`bt-status is-${p.status}`}>{p.status}</span>
                    </td>
                    <td className="bt-amount">{formatAmount(p)}</td>
                    <td className="bt-provider">{p.provider}</td>
                    <td>
                      <code className="bt-ref">{p.payment_ref || '—'}</code>
                    </td>
                    <td className="bt-date">{new Date(p.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppShell>
  )
}
