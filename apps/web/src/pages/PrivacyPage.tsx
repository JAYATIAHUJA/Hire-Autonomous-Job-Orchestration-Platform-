import { Link } from 'react-router-dom'
import NoticeContent from '../components/NoticeContent'

// Public: anyone can read the notice before signing in.
export default function PrivacyPage() {
  return (
    <section className="auth-page notice-page">
      <div className="card">
        <NoticeContent />
      </div>
      <Link to="/login" className="ghost-button">
        Back to sign in
      </Link>
    </section>
  )
}
