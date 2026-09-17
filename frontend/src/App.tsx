import { Link, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">HIRE</Link>
        <span className="tagline">Proof-of-work profiles from real GitHub history</span>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  )
}
