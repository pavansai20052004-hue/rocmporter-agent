import { getApiUrl } from './api'

// Which payment provider is active on the backend (razorpay | stripe).
export async function getBillingConfig() {
  try {
    const res = await fetch(getApiUrl('/api/billing/config'))
    if (res.ok) return await res.json()
  } catch {
    /* fall through */
  }
  return { provider: 'stripe' }
}

function loadRazorpayScript() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve()
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Could not load the Razorpay checkout.'))
    document.body.appendChild(script)
  })
}

// Razorpay flow: create an order, open the checkout modal, verify server-side.
async function razorpayCheckout(accessToken, user) {
  const orderRes = await fetch(getApiUrl('/api/billing/razorpay/order'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  })
  if (!orderRes.ok) {
    let detail = 'Could not start the payment.'
    try {
      detail = (await orderRes.json()).detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const order = await orderRes.json()
  await loadRazorpayScript()

  return new Promise((resolve, reject) => {
    const rzp = new window.Razorpay({
      key: order.keyId,
      order_id: order.orderId,
      amount: order.amount,
      currency: order.currency,
      name: 'ROCmPorter Pro',
      description: '31 days of Pro — AI patches & migration PRs',
      prefill: { email: user?.email ?? '' },
      theme: { color: '#e31837' },
      modal: {
        ondismiss: () => reject(new Error('Payment cancelled.')),
      },
      handler: async (resp) => {
        try {
          const verifyRes = await fetch(getApiUrl('/api/billing/razorpay/verify'), {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            },
            body: JSON.stringify({
              orderId: resp.razorpay_order_id,
              paymentId: resp.razorpay_payment_id,
              signature: resp.razorpay_signature,
            }),
          })
          if (!verifyRes.ok) {
            const data = await verifyRes.json().catch(() => ({}))
            throw new Error(data.detail || 'Payment verification failed.')
          }
          resolve(await verifyRes.json())
        } catch (err) {
          reject(err)
        }
      },
    })
    rzp.open()
  })
}

// Opens the Stripe Billing Portal so a Pro user can manage or cancel billing.
export async function openPortal(accessToken) {
  const res = await fetch(getApiUrl('/api/billing/portal'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ returnUrl: `${window.location.origin}/dashboard` }),
  })
  if (!res.ok) {
    let detail = 'Could not open the billing portal.'
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const data = await res.json()
  if (data.url) window.location.href = data.url
}

// Kicks off checkout with whichever provider the backend has configured.
// Razorpay opens an in-page modal and resolves after server-side verification;
// Stripe redirects to its hosted checkout page.
export async function startCheckout(plan, accessToken, user) {
  const config = await getBillingConfig()
  if (config.provider === 'razorpay') {
    return razorpayCheckout(accessToken, user)
  }
  return stripeCheckout(plan, accessToken)
}

async function stripeCheckout(plan, accessToken) {
  const res = await fetch(getApiUrl('/api/billing/checkout'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ plan, successUrl: `${window.location.origin}/app`, cancelUrl: `${window.location.origin}/#pricing` }),
  })
  if (!res.ok) {
    let detail = 'Could not start checkout.'
    try {
      const data = await res.json()
      detail = data.detail || data.message || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const data = await res.json()
  if (data.url) {
    window.location.href = data.url
  } else {
    throw new Error('Checkout session did not return a URL.')
  }
}
