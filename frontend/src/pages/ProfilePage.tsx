import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getProfile } from '../api/client'
import CommitTimelineChart from '../components/CommitTimelineChart'
import SkillCard from '../components/SkillCard'
import StatsHeader from '../components/StatsHeader'
import type { Profile } from '../types'

export default function ProfilePage() {
  const { profileId } = useParams()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!profileId) return
    getProfile(profileId)
      .then(setProfile)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load profile.'))
  }, [profileId])

  if (error) return <p className="error">{error}</p>
  if (!profile) return <p className="muted">Loading profile…</p>

  return (
    <div className="profile-page">
      <StatsHeader profile={profile} />
      <CommitTimelineChart timeline={profile.timeline} />

      <h2>Skills &amp; evidence</h2>
      <p className="muted">
        Confidence reflects how much evidence we found (commits, repositories, recency) — not a rating of ability.
      </p>
      {profile.skills.length === 0 ? (
        <p className="muted">No authored commits found in the analyzed repositories yet.</p>
      ) : (
        <div className="skill-grid">
          {profile.skills.map((skill) => (
            <SkillCard key={skill.name} skill={skill} />
          ))}
        </div>
      )}
    </div>
  )
}
