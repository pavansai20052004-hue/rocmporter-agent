# Enabling Login, GitHub Repos & Live Pricing

Everything is already coded. You just create a few free accounts and paste the
keys. Until you do, the app still works as an open scanner (auth stays dormant).

There are **3 setups**: Supabase (login + DB + repos), OAuth apps (Google +
GitHub), and Stripe (payments). Do them in order.

---

## 1) Supabase — login, database, GitHub repo access

1. Go to <https://supabase.com> → **New project** (free). Pick a name + strong DB password.
2. When it's ready, open **Project Settings → API** and copy:
   - **Project URL** → this is `VITE_SUPABASE_URL`
   - **anon public** key → this is `VITE_SUPABASE_ANON_KEY`
3. Open **SQL Editor → New query**, paste the contents of [`supabase/schema.sql`](supabase/schema.sql), and click **Run**. (Creates the profiles/scans tables.)
4. Open **Authentication → URL Configuration** and add these to **Redirect URLs**:
   - `https://rocmporter-agent.vercel.app/app`
   - `http://localhost:5173/app` (for local dev)

Now the OAuth providers 👇

### 1a) Google sign-in
1. Go to <https://console.cloud.google.com> → create a project → **APIs & Services → Credentials**.
2. **Create Credentials → OAuth client ID → Web application**.
3. Under **Authorized redirect URIs**, add the callback Supabase shows you:
   `https://YOUR-PROJECT.supabase.co/auth/v1/callback`
4. Copy the **Client ID** and **Client secret**.
5. In Supabase → **Authentication → Providers → Google** → enable → paste Client ID + secret → Save.

### 1b) GitHub sign-in (+ repo access)
1. Go to <https://github.com/settings/developers> → **OAuth Apps → New OAuth App**.
2. **Homepage URL:** `https://rocmporter-agent.vercel.app`
   **Authorization callback URL:** `https://YOUR-PROJECT.supabase.co/auth/v1/callback`
3. Create it, then **Generate a new client secret**. Copy Client ID + secret.
4. In Supabase → **Authentication → Providers → GitHub** → enable → paste Client ID + secret → Save.

> The app requests the `repo` scope, so after a user signs in with GitHub it can list and scan their private repos.

---

## 2) Stripe — live pricing / checkout

1. Go to <https://dashboard.stripe.com> and stay in **Test mode** (toggle, top-right) for now.
2. **Products → Add product** → name "ROCmPorter Pro" → add a **recurring** price ($29/month) → Save.
   Copy the **price id** (`price_...`) → this is `STRIPE_PRICE_PRO`.
3. **Developers → API keys** → copy the **Secret key** (`sk_test_...`) → this is `STRIPE_SECRET_KEY`.
4. (Optional, for subscription tracking) **Developers → Webhooks → Add endpoint**:
   - URL: `https://rocmporter-api.onrender.com/api/billing/webhook`
   - Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
   - Copy the **Signing secret** (`whsec_...`) → this is `STRIPE_WEBHOOK_SECRET`.

---

## 3) Where to paste each key

**Vercel** (Project → Settings → Environment Variables → Production), then redeploy:
| Key | Value |
|-----|-------|
| `VITE_SUPABASE_URL` | your Supabase Project URL |
| `VITE_SUPABASE_ANON_KEY` | your Supabase anon key |
| `VITE_API_BASE_URL` | `https://rocmporter-api.onrender.com` (already set) |

**Render** (your `rocmporter-api` service → Environment):
| Key | Value |
|-----|-------|
| `STRIPE_SECRET_KEY` | `sk_test_...` |
| `STRIPE_PRICE_PRO` | `price_...` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` (if you made a webhook) |

---

## 4) Test it

- **Login:** open the site → **Sign in** → Google or GitHub → you land on `/app`.
- **Repos:** top bar → **My repos** → your GitHub repos list → **Scan** any one.
- **Pricing:** landing page → **Upgrade to Pro** → Stripe checkout. Use test card
  `4242 4242 4242 4242`, any future expiry, any CVC.

When you've created the Supabase project, send me `VITE_SUPABASE_URL` and
`VITE_SUPABASE_ANON_KEY` (the anon key is public/safe) and I'll rebuild the
frontend so login goes live immediately.
