import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { Alert, Loading } from '../ui/kit'
import { useAuth } from './AuthContext'
import { decideRoute, type RouteKind } from './guard'

export function RouteGuard({ route, children }: { route: RouteKind; children?: ReactNode }) {
  const { auth, refresh } = useAuth()
  const location = useLocation()
  const [params] = useSearchParams()
  const decision = decideRoute(auth, route, { path: `${location.pathname}${location.search}`, next: params.get('next') })

  if (decision.kind === 'wait') {
    return (
      <div className="center-state">
        <Loading label="Loading your account…" />
      </div>
    )
  }
  if (decision.kind === 'error') {
    return (
      <div className="center-state">
        <div className="card card-pad stack" style={{ maxWidth: 420 }}>
          <h2>Can’t reach Hire right now</h2>
          <Alert tone="error">{decision.message}</Alert>
          <p className="muted small">Check that the API is running, then try again. You have not been logged out.</p>
          <button type="button" className="btn btn-primary" onClick={() => refresh()}>
            Try again
          </button>
        </div>
      </div>
    )
  }
  if (decision.kind === 'redirect') return <Navigate to={decision.to} replace />
  return children ? <>{children}</> : <Outlet />
}
