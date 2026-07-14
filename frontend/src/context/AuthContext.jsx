import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { isSupabaseConfigured, supabase } from '../lib/supabase'

const AuthContext = createContext(null)

const GH_TOKEN_KEY = 'rocmporter_gh_provider_token'

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [plan, setPlan] = useState('free')
  // GitHub OAuth returns the provider access token only on the initial sign-in
  // event, so we persist it separately to keep listing repos across reloads.
  const [providerToken, setProviderToken] = useState(
    () => (typeof localStorage !== 'undefined' ? localStorage.getItem(GH_TOKEN_KEY) : null),
  )

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setLoading(false)
      return undefined
    }

    // onAuthStateChange fires an INITIAL_SESSION event *after* Supabase has
    // parsed any OAuth token/code from the URL, so it's the reliable source of
    // truth for the initial load. getSession() is a fallback.
    const { data: listener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession)
      setLoading(false)
      if (nextSession?.provider_token) {
        setProviderToken(nextSession.provider_token)
        try {
          localStorage.setItem(GH_TOKEN_KEY, nextSession.provider_token)
        } catch {
          /* ignore storage errors */
        }
      }
      if (event === 'SIGNED_OUT') {
        setProviderToken(null)
        try {
          localStorage.removeItem(GH_TOKEN_KEY)
        } catch {
          /* ignore storage errors */
        }
      }
    })

    // Safety fallback: if no auth event has fired within a moment, stop showing
    // the loading state so the app never hangs.
    supabase.auth.getSession().then(({ data }) => {
      setSession((current) => current ?? data.session)
      setLoading(false)
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  const signInWithGoogle = useCallback(async () => {
    if (!isSupabaseConfigured) return
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/app` },
    })
  }, [])

  const signInWithGitHub = useCallback(async () => {
    if (!isSupabaseConfigured) return
    await supabase.auth.signInWithOAuth({
      provider: 'github',
      options: {
        // read access to public + private repos so the user can scan any of theirs
        scopes: 'read:user repo',
        redirectTo: `${window.location.origin}/app`,
      },
    })
  }, [])

  const signOut = useCallback(async () => {
    if (!isSupabaseConfigured) return
    await supabase.auth.signOut()
    setPlan('free')
  }, [])

  const userId = session?.user?.id ?? null

  const refreshProfile = useCallback(async () => {
    if (!isSupabaseConfigured || !userId) {
      setPlan('free')
      return
    }
    const { data } = await supabase.from('profiles').select('plan').eq('id', userId).maybeSingle()
    setPlan(data?.plan ?? 'free')
  }, [userId])

  // Load the plan whenever the user changes, and again when the tab regains
  // focus (e.g. returning from Stripe checkout in another tab).
  useEffect(() => {
    refreshProfile()
    const onFocus = () => refreshProfile()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refreshProfile])

  const value = {
    session,
    user: session?.user ?? null,
    accessToken: session?.access_token ?? null,
    providerToken,
    plan,
    isPro: plan === 'pro' || plan === 'team',
    refreshProfile,
    loading,
    isConfigured: isSupabaseConfigured,
    signInWithGoogle,
    signInWithGitHub,
    signOut,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
