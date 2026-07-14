import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { isSupabaseConfigured, supabase } from '../lib/supabase'

const AuthContext = createContext(null)

const GH_TOKEN_KEY = 'rocmporter_gh_provider_token'

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
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

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    const { data: listener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession)
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
  }, [])

  const value = {
    session,
    user: session?.user ?? null,
    accessToken: session?.access_token ?? null,
    providerToken,
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
