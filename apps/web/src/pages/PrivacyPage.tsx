import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import NoticeContent from '../components/NoticeContent'
import Icon from '../ui/Icon'

// Public: anyone can read the notice before signing in.
export default function PrivacyPage() {
  const { auth } = useAuth()
  const signedIn = auth.status === 'authenticated'
  return (
    <div className="page page-narrow">
      <Link to={signedIn ? '/profile' : '/login'} className="btn btn-ghost btn-sm" style={{ marginBottom: 16, marginLeft: -12 }}>
        <Icon name="arrowLeft" size={15} />
        {signedIn ? 'Back to your profile' : 'Back to sign in'}
      </Link>
      <div className="card card-pad-lg notice-content">
        <NoticeContent />
      </div>
    </div>
  )
}
