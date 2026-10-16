import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { accountApi } from '../api/account'
import type { Me } from '../api/v1types'
import type { AuthState } from './guard'

type AuthContextValue = {
  auth: AuthState
  refresh: () => Promise<void>
  setMe: (me: Me) => void
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' })

  const refresh = useCallback(async () => {
    try {
      const me = await accountApi.getMe()
      setAuth(me ? { status: 'authenticated', me } : { status: 'anonymous' })
    } catch (err) {
      // A network error is not a logout: keep the user where they are and let them retry.
      setAuth({ status: 'error', message: err instanceof Error ? err.message : 'Could not reach Hire.' })
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const setMe = useCallback((me: Me) => setAuth({ status: 'authenticated', me }), [])

  const logout = useCallback(async () => {
    try {
      await accountApi.logout()
    } finally {
      setAuth({ status: 'anonymous' })
    }
  }, [])

  const value = useMemo(() => ({ auth, refresh, setMe, logout }), [auth, refresh, setMe, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
