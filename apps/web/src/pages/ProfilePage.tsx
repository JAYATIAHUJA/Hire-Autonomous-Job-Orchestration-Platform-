import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProfile } from '../api/client'
import ProfileView from '../components/ProfileView'
import type { Profile } from '../types'
import Icon from '../ui/Icon'
import { Alert, errorMessage, Loading, PageHeader } from '../ui/kit'

// A saved analysis opened by id (old links). Your own lives at /profile.
export default function ProfilePage() {
  const { profileId } = useParams()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!profileId) return
    getProfile(profileId)
      .then(setProfile)
      .catch((err) => setError(errorMessage(err, 'Could not load this analysis.')))
  }, [profileId])

  return (
    <div className="page">
      <PageHeader
        eyebrow="Proof of work"
        title={profile ? `@${profile.username}` : 'GitHub analysis'}
        actions={
          <Link to="/profile" className="btn btn-secondary">
            <Icon name="arrowLeft" size={16} />
            Your profile
          </Link>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : !profile ? <Loading label="Loading analysis…" /> : <ProfileView profile={profile} />}
    </div>
  )
}
