import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { decideRoute, type RouteKind } from './guard'

export function RouteGuard({ route, children }: { route: RouteKind; children?: ReactNode }) {
  const { auth, refresh } = useAuth()
  const location = useLocation()
  const [params] = useSearchParams()
  const decision = decideRoute(auth, route, { path: `${location.pathname}${location.search}`, next: params.get('next') })

  if (decision.kind === 'wait') {
    return (
      <div className="guard-wait" role="status" aria-live="polite">
        Loading your account…
      </div>
    )
  }
  if (decision.kind === 'error') {
    return (
      <div className="card guard-error" role="alert">
        <p className="error">Could not reach Hire: {decision.message}</p>
        <button type="button" onClick={() => refresh()}>
          Try again
        </button>
      </div>
    )
  }
  if (decision.kind === 'redirect') return <Navigate to={decision.to} replace />
  return children ? <>{children}</> : <Outlet />
}
