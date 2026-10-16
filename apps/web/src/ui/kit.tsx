import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import Icon, { type IconName } from './Icon'

/* ---- Page header: what this screen is and what you can do here ---------------------- */

type PageHeaderProps = {
  eyebrow?: string
  title: ReactNode
  lede?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, lede, actions }: PageHeaderProps) {
  return (
    <header className="page-head">
      <div className="page-head-text">
        {eyebrow && (
          <span className="eyebrow">
            <span className="eyebrow-dot" aria-hidden="true" />
            {eyebrow}
          </span>
        )}
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}

/* ---- Explainer: shown until the user says "Got it", then folded to a small link ----- */

const dismissKey = (id: string) => `hire.explainer.${id}`

function readDismissed(id: string): boolean {
  try {
    return window.localStorage.getItem(dismissKey(id)) === '1'
  } catch {
    return false
  }
}

function writeDismissed(id: string, value: boolean) {
  try {
    if (value) window.localStorage.setItem(dismissKey(id), '1')
    else window.localStorage.removeItem(dismissKey(id))
  } catch {
    // Private browsing: it simply shows again next visit.
  }
}

export type ExplainerStep = { title: string; body: ReactNode }

export function Explainer({ id, title, steps }: { id: string; title: string; steps: ExplainerStep[] }) {
  const [dismissed, setDismissed] = useState(() => readDismissed(id))

  if (dismissed) {
    return (
      <div style={{ marginTop: -8, marginBottom: 20 }}>
        <button
          type="button"
          className="help-toggle"
          onClick={() => {
            writeDismissed(id, false)
            setDismissed(false)
          }}
        >
          <Icon name="help" size={15} />
          {title}
        </button>
      </div>
    )
  }

  return (
    <section className="explainer" aria-label={title}>
      <div className="explainer-head">
        <span className="explainer-title">
          <Icon name="sparkle" size={16} />
          {title}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => {
            writeDismissed(id, true)
            setDismissed(true)
          }}
        >
          Got it
        </button>
      </div>
      <ol className="explainer-steps">
        {steps.map((s) => (
          <li key={s.title}>
            <span>
              <strong>{s.title}</strong>
              {s.body}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

/* ---- States ------------------------------------------------------------------------- */

export function EmptyState({
  icon,
  title,
  children,
  actions,
}: {
  icon: IconName
  title: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {actions && <div className="row">{actions}</div>}
    </div>
  )
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="loading-block" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  )
}

export function Alert({
  tone = 'info',
  children,
  id,
}: {
  tone?: 'info' | 'error' | 'warn' | 'good'
  children: ReactNode
  id?: string
}) {
  const icon: IconName = tone === 'error' || tone === 'warn' ? 'alert' : tone === 'good' ? 'check' : 'info'
  return (
    <div id={id} className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon name={icon} size={16} />
      <div>{children}</div>
    </div>
  )
}

export function Meter({ value, tone }: { value: number; tone?: 'good' | 'warn' | 'accent' }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)))
  return (
    <div className={`meter${tone ? ` meter-${tone}` : ''}`} aria-hidden="true">
      <div className="meter-fill" style={{ width: `${pct}%` }} />
    </div>
  )
}

/* ---- Identity helpers --------------------------------------------------------------- */

export function initials(text: string | null | undefined): string {
  const clean = (text || '').replace(/@.*/, '').replace(/[^a-zA-Z0-9 ._-]/g, ' ').trim()
  if (!clean) return '?'
  // Words that start with a letter: "aarav-1792" gives "A", not "A1".
  const parts = clean.split(/[ ._-]+/).filter((w) => /^[a-zA-Z]/.test(w))
  if (parts.length === 0) return clean[0].toUpperCase()
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || clean[0].toUpperCase()
}

export function LogoTile({ name, small }: { name: string; small?: boolean }) {
  return (
    <span className={`logo-tile${small ? ' sm' : ''}`} aria-hidden="true">
      {(name.trim()[0] || '?').toUpperCase()}
    </span>
  )
}

// A name to greet someone by. Email-only accounts get their display name set to the
// address itself, so an "@" means there is no real name: use the mailbox's first word.
export function firstName(display: string | null | undefined, email: string | null | undefined): string | null {
  const shown = display?.trim()
  if (shown && !shown.includes('@')) return shown.split(/\s+/)[0]
  const address = shown || email
  if (!address) return null
  const local = address.split('@')[0].split(/[._\-+0-9]/).find(Boolean)
  return local ? local[0].toUpperCase() + local.slice(1).toLowerCase() : null
}

// A full display name, or null when the account only has an email.
export function realName(display: string | null | undefined): string | null {
  const shown = display?.trim()
  return shown && !shown.includes('@') ? shown : null
}

/* ---- Toasts ------------------------------------------------------------------------- */

type ToastAction = { label: string; href: string }

type Toast = { id: number; title: string; body?: string; action?: ToastAction }

type ToastApi = { show: (title: string, body?: string, action?: ToastAction) => void }

const ToastContext = createContext<ToastApi | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(1)

  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), [])

  const show = useCallback(
    (title: string, body?: string, action?: ToastAction) => {
      const id = next.current++
      setToasts((all) => [...all.slice(-2), { id, title, body, action }])
      window.setTimeout(() => dismiss(id), action ? 9000 : 5000)
    },
    [dismiss],
  )

  const api = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-wrap" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast" role="status">
            <span className="toast-icon">
              <Icon name="check" size={13} stroke={3} />
            </span>
            <div className="toast-body">
              <strong>{t.title}</strong>
              {t.body && <span>{t.body}</span>}
            </div>
            {t.action && (
              <a href={t.action.href} target="_blank" rel="noreferrer" className="toast-action">
                {t.action.label}
              </a>
            )}
            <button type="button" className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <Icon name="x" size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) throw new Error('useToast must be used inside <ToastProvider>')
  return api
}

/* ---- Formatting --------------------------------------------------------------------- */

export function ago(days: number): string {
  if (days <= 0) return 'Posted today'
  if (days === 1) return 'Posted yesterday'
  if (days < 30) return `Posted ${days} days ago`
  const months = Math.round(days / 30)
  return `Posted ${months} month${months === 1 ? '' : 's'} ago`
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}
