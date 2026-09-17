import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { analyzeProfile, ApiError } from '../api/client'

export default function ConnectPage() {
  const [username, setUsername] = useState('')
  const [token, setToken] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!username.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await analyzeProfile(username.trim(), token.trim() || undefined)
      navigate(`/profile/${result.profile_id}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError('GitHub rate limit reached. Add a personal access token and try again.')
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="connect-page">
      <h1>Turn your GitHub into a proof-of-work profile</h1>
      <p className="subtitle">
        We read your repositories, commits and pull requests and turn them into a skills profile where every
        claim links back to real work — no self-reported ratings, no opaque scores.
      </p>

      <form onSubmit={handleSubmit} className="card connect-form">
        <label>
          GitHub username
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="octocat" required />
        </label>
        <label>
          Personal access token <span className="muted">(optional)</span>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="ghp_…"
            autoComplete="off"
          />
        </label>
        <p className="hint">
          We read the actual diffs of your commits and merged pull requests. Without a token GitHub allows only 60
          requests/hour, so just 3 repositories are sampled; with a token up to 20 repositories and your merged PRs to
          other projects are analyzed. The token is used for this one analysis and never stored.
        </p>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={loading}>
          {loading ? 'Reading your commits and pull requests… (can take up to a minute)' : 'Build my profile'}
        </button>
      </form>
    </section>
  )
}
