import { getApiUrl } from './api'

// Kicks off a Stripe Checkout session on the backend and redirects the browser
// to Stripe's hosted checkout page.
export async function startCheckout(plan, accessToken) {
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
