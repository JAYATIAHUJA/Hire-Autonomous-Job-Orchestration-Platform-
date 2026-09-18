import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProfile } from '../api/client'
import CommitTimelineChart from '../components/CommitTimelineChart'
import ContributionItem from '../components/ContributionItem'
import ProjectsTable from '../components/ProjectsTable'
import SkillCard from '../components/SkillCard'
import StatsHeader from '../components/StatsHeader'
import WorkMixBar from '../components/WorkMixBar'
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

      <div className="card proof-jobs-cta">
        <div className="proof-jobs-cta-text">
          <span className="banner-badge">Verified Skills Ready</span>
          <h3>Deploy your Proof-of-Work to Verified Jobs</h3>
          <p className="muted">
            Match your code-backed skills with 100% ghost-free, verified engineering roles.
          </p>
        </div>
        <Link to="/jobs" className="btn-browse-jobs">
          Explore Verified Jobs ➔
        </Link>
      </div>

      {profile.top_contributions.length > 0 && (
        <section className="card">
          <h2>Strongest proof of work</h2>
          <ul className="contribution-list">
            {profile.top_contributions.map((c) => (
              <ContributionItem key={c.url} contribution={c} />
            ))}
          </ul>
        </section>
      )}

      <div className="two-col">
        <WorkMixBar mix={profile.work_mix} />
        <CommitTimelineChart timeline={profile.timeline} />
      </div>

      <ProjectsTable projects={profile.projects} />

      <h2>Skills &amp; evidence</h2>
      <p className="muted">
        Skills are detected only from changes you made: the files you touched, the libraries you imported and the
        dependencies you added. The tier shows how much evidence there is, not how good you are.
      </p>
      {profile.skills.length === 0 ? (
        <p className="muted">No skill evidence found in the analyzed contributions yet.</p>
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
