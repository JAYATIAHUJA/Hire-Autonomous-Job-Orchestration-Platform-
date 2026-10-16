import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { LOGIN_PATH, onboardingComplete } from './auth/guard'
import Icon, { type IconName } from './ui/Icon'
import { initials, realName, ToastProvider } from './ui/kit'

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: '/', label: 'Home', icon: 'home', end: true },
  { to: '/swipe', label: 'Deck', icon: 'deck' },
  { to: '/jobs', label: 'Jobs', icon: 'briefcase' },
  { to: '/pipeline', label: 'Pipeline', icon: 'board' },
  { to: '/profile', label: 'Profile', icon: 'user' },
]

export default function App() {
  const { auth } = useAuth()
  const me = auth.status === 'authenticated' ? auth.me : null
  // Until onboarding is done the app pages are guarded anyway; hide their links.
  const inApp = me !== null && onboardingComplete(me)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // A new screen starts at the top.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])

  // The public website brings its own header and footer.
  if (auth.status === 'anonymous' && location.pathname === '/') {
    return (
      <ToastProvider>
        <Outlet />
      </ToastProvider>
    )
  }

  return (
    <ToastProvider>
      <div className={`shell${inApp ? ' has-tabbar has-sidebar' : ''}`}>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <header className={`topbar${scrolled ? ' scrolled' : ''}`}>
          <Link to="/" className="brand" aria-label="Hire home">
            <span className="brand-mark" aria-hidden="true" />
            hire
          </Link>
          {inApp && (
            <nav className="nav" aria-label="Main">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          )}
          <div className="topbar-right">
            {me ? (
              <AccountMenu email={me.email} name={realName(me.display_name)} />
            ) : (
              location.pathname !== '/privacy' && (
                <Link to="/privacy" className="btn btn-ghost btn-sm">
                  Privacy
                </Link>
              )
            )}
          </div>
        </header>

        {inApp && <Sidebar email={me!.email} name={realName(me!.display_name)} />}

        <main id="main" className="main" tabIndex={-1}>
          <Outlet />
        </main>

        {inApp && (
          <nav className="tabbar" aria-label="Main">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
                <Icon name={item.icon} size={21} />
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}
      </div>
    </ToastProvider>
  )
}

function Sidebar({ email, name }: { email: string | null; name: string | null }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  return (
    <aside className="sidebar" aria-label="Main">
      <Link to="/" className="sidebar-logo" aria-label="Hire home">
        <span className="brand-mark" aria-hidden="true" />
      </Link>
      <nav className="sidebar-nav">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
            aria-label={item.label}
          >
            <Icon name={item.icon} size={20} />
            <span className="sidebar-tip">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-foot">
        <Link to="/profile" className="sidebar-avatar" title={name || email || 'Your profile'}>
          {initials(name || email)}
        </Link>
        <button
          type="button"
          className="sidebar-link"
          aria-label="Log out"
          onClick={async () => {
            await logout()
            navigate(LOGIN_PATH, { replace: true })
          }}
        >
          <Icon name="logout" size={19} />
          <span className="sidebar-tip">Log out</span>
        </button>
      </div>
    </aside>
  )
}

function AccountMenu({ email, name }: { email: string | null; name: string | null }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  async function onLogout() {
    setOpen(false)
    await logout()
    navigate(LOGIN_PATH, { replace: true })
  }

  const label = name || email || 'Your account'

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        className="avatar-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="avatar-email">{email ?? name ?? 'Account'}</span>
        <span className="avatar" aria-hidden="true">
          {initials(name || email)}
        </span>
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <strong style={{ display: 'block', fontSize: '0.9rem' }}>{label}</strong>
            {email && name && <span className="muted small">{email}</span>}
          </div>
          <Link to="/profile" className="menu-item" role="menuitem" onClick={() => setOpen(false)}>
            <Icon name="user" size={16} />
            Your profile
          </Link>
          <Link to="/privacy" className="menu-item" role="menuitem" onClick={() => setOpen(false)}>
            <Icon name="shield" size={16} />
            Privacy notice
          </Link>
          <button type="button" className="menu-item" role="menuitem" onClick={onLogout}>
            <Icon name="logout" size={16} />
            Log out
          </button>
        </div>
      )}
    </div>
  )
}
