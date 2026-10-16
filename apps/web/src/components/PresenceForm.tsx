import { useEffect, useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { OnlinePresence, OtherLink } from '../api/v1types'
import Icon, { type IconName } from '../ui/Icon'
import { Alert, errorMessage, Loading } from '../ui/kit'

// GitHub's page for a new fine-grained token.
const TOKEN_URL = 'https://github.com/settings/personal-access-tokens/new'

type Basics = { name: string; phone: string; location: string }

const BASIC_KINDS: [keyof Basics, string][] = [
  ['name', 'name'],
  ['phone', 'contact_phone'],
  ['location', 'location'],
]

const OTHER_IDEAS = ['X / Twitter', 'LeetCode', 'Kaggle', 'Stack Overflow', 'Medium', 'Dev.to', 'Behance', 'Dribbble']

type Props = {
  // Whether the user allowed GitHub analysis; the token field only makes sense then.
  githubAllowed: boolean
  submitLabel?: string
  onSaved: (saved: OnlinePresence) => void
  onCancel?: () => void
  onSkip?: () => void
}

function Field({
  icon,
  label,
  optional,
  hint,
  children,
}: {
  icon: IconName
  label: string
  optional?: boolean
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="field">
      <span className="field-label row" style={{ gap: 7 }}>
        <Icon name={icon} size={15} />
        {label}
        {optional && <span className="optional">optional</span>}
      </span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  )
}

export default function PresenceForm({ githubAllowed, submitLabel = 'Save', onSaved, onCancel, onSkip }: Props) {
  const [loaded, setLoaded] = useState(false)
  const [username, setUsername] = useState('')
  const [token, setToken] = useState('')
  const [tokenSaved, setTokenSaved] = useState(false)
  const [linkedin, setLinkedin] = useState('')
  const [website, setWebsite] = useState('')
  const [portfolio, setPortfolio] = useState('')
  const [others, setOthers] = useState<OtherLink[]>([])
  const [fromResume, setFromResume] = useState(false)
  // Basics live on the profile as name / phone / location facts; null = not loaded.
  const [basics, setBasics] = useState<Basics>({ name: '', phone: '', location: '' })
  const [savedBasics, setSavedBasics] = useState<Basics>({ name: '', phone: '', location: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    accountApi
      .getProfile()
      .then((profile) => {
        const id = profile.profile.identity
        const b = { name: id?.name?.value ?? '', phone: id?.phone?.value ?? '', location: id?.location?.value ?? '' }
        if (!cancelled) {
          setBasics(b)
          setSavedBasics(b)
        }
      })
      .catch(() => undefined)
    accountApi
      .getPresence()
      .then((p) => {
        if (cancelled) return
        setFromResume(Boolean(p.from_resume))
        setUsername(p.github_username ?? '')
        setTokenSaved(p.github_token_saved)
        setLinkedin(p.linkedin ?? '')
        setWebsite(p.website ?? '')
        setPortfolio(p.portfolio ?? '')
        setOthers(p.others)
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const setOther = (i: number, patch: Partial<OtherLink>) =>
    setOthers((all) => all.map((o, j) => (j === i ? { ...o, ...patch } : o)))

  async function save(clearToken = false) {
    setBusy(true)
    setError(null)
    try {
      // Changed basics become the user's own facts (a new one retires the old).
      for (const [field, kind] of BASIC_KINDS) {
        const value = basics[field].trim()
        if (value && value !== savedBasics[field]) await accountApi.addFact(kind, value)
      }
      setSavedBasics(basics)
      const saved = await accountApi.savePresence({
        github_username: username.trim() || null,
        github_token: token.trim() || null,
        clear_github_token: clearToken,
        linkedin: linkedin.trim() || null,
        website: website.trim() || null,
        portfolio: portfolio.trim() || null,
        others: others.filter((o) => o.url.trim()).map((o) => ({ label: o.label.trim() || 'Link', url: o.url.trim() })),
      })
      setToken('')
      setTokenSaved(saved.github_token_saved)
      setUsername(saved.github_username ?? '')
      setFromResume(false)
      onSaved(saved)
    } catch (err) {
      setError(errorMessage(err, 'Could not save your profiles.'))
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    save()
  }

  if (!loaded) return <Loading label="Loading your profiles…" />

  const unusedIdeas = OTHER_IDEAS.filter((idea) => !others.some((o) => o.label.toLowerCase() === idea.toLowerCase()))

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      {fromResume && (
        <Alert tone="good">We filled in the links we found in your resume. Check them, add anything missing, and save.</Alert>
      )}
      <section className="card card-pad stack" style={{ gap: 16, boxShadow: 'none' }}>
        <h3>The basics</h3>
        <Field icon="user" label="Full name">
          <input className="input" value={basics.name} onChange={(e) => setBasics({ ...basics, name: e.target.value })} placeholder="Priya Sharma" autoComplete="name" />
        </Field>
        <div className="grid grid-2" style={{ gap: 16 }}>
          <Field icon="phone" label="Phone" optional>
            <input
              className="input"
              value={basics.phone}
              onChange={(e) => setBasics({ ...basics, phone: e.target.value })}
              placeholder="+91 98765 43210"
              inputMode="tel"
              autoComplete="tel"
            />
          </Field>
          <Field icon="pin" label="City">
            <input
              className="input"
              value={basics.location}
              onChange={(e) => setBasics({ ...basics, location: e.target.value })}
              placeholder="Bengaluru"
              autoComplete="address-level2"
            />
          </Field>
        </div>
      </section>

      <section className="card card-pad stack" style={{ gap: 16, boxShadow: 'none' }}>
        <div className="row-between">
          <h3 className="row" style={{ gap: 8 }}>
            <Icon name="github" size={18} />
            GitHub
          </h3>
          {tokenSaved && <span className="badge badge-good">Token verified</span>}
        </div>
        <Field icon="user" label="GitHub username" hint="Your code is the proof behind your skills.">
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="octocat"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
          />
        </Field>

        {githubAllowed ? (
          <Field icon="key" label="Personal access token" optional>
            <input
              className="input"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={tokenSaved ? '•••••••• saved — paste a new one to replace it' : 'github_pat_…'}
              autoComplete="off"
              spellCheck={false}
            />
            <span className="hint">
              Without a token GitHub lets us read only a few repositories. With one we analyse up to 20 and your merged
              pull requests to other projects.{' '}
              <a href={TOKEN_URL} target="_blank" rel="noreferrer" className="text-link">
                Create a token
              </a>{' '}
              → choose <strong>Public repositories (read-only)</strong>, no other permissions. We check it with GitHub,
              store it encrypted, and never show it again.
            </span>
            {tokenSaved && (
              <button type="button" className="link-btn small" style={{ alignSelf: 'flex-start' }} disabled={busy} onClick={() => save(true)}>
                Remove saved token
              </button>
            )}
          </Field>
        ) : (
          <p className="hint">
            GitHub analysis is switched off in your privacy settings, so we only keep your username as a link.
          </p>
        )}
      </section>

      <section className="card card-pad stack" style={{ gap: 16, boxShadow: 'none' }}>
        <h3>Everywhere else</h3>
        <Field icon="linkedin" label="LinkedIn" optional>
          <input
            className="input"
            value={linkedin}
            onChange={(e) => setLinkedin(e.target.value)}
            placeholder="linkedin.com/in/your-name"
            autoComplete="off"
            autoCapitalize="none"
          />
        </Field>
        <div className="grid grid-2" style={{ gap: 16 }}>
          <Field icon="globe" label="Website" optional>
            <input
              className="input"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="yourname.dev"
              inputMode="url"
              autoCapitalize="none"
            />
          </Field>
          <Field icon="palette" label="Portfolio" optional>
            <input
              className="input"
              value={portfolio}
              onChange={(e) => setPortfolio(e.target.value)}
              placeholder="behance.net/you"
              inputMode="url"
              autoCapitalize="none"
            />
          </Field>
        </div>

        <div className="field">
          <span className="field-label row" style={{ gap: 7 }}>
            <Icon name="link" size={15} />
            Other profiles<span className="optional">optional</span>
          </span>
          {others.map((o, i) => (
            <div key={i} className="row" style={{ flexWrap: 'nowrap', gap: 8 }}>
              <input
                className="input"
                style={{ width: 150, flex: 'none' }}
                value={o.label}
                onChange={(e) => setOther(i, { label: e.target.value })}
                placeholder="Name"
                aria-label="Profile name"
              />
              <input
                className="input"
                value={o.url}
                onChange={(e) => setOther(i, { url: e.target.value })}
                placeholder="Link"
                inputMode="url"
                autoCapitalize="none"
                aria-label={`${o.label || 'Profile'} link`}
              />
              <button
                type="button"
                className="btn btn-ghost btn-icon"
                aria-label={`Remove ${o.label || 'profile'}`}
                onClick={() => setOthers((all) => all.filter((_, j) => j !== i))}
              >
                <Icon name="trash" size={16} />
              </button>
            </div>
          ))}
          {others.length < 10 && (
            <div className="chips-preview">
              {unusedIdeas.slice(0, 6).map((idea) => (
                <button
                  key={idea}
                  type="button"
                  className="chip chip-outline"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setOthers((all) => [...all, { label: idea, url: '' }])}
                >
                  + {idea}
                </button>
              ))}
              <button
                type="button"
                className="chip chip-outline"
                style={{ cursor: 'pointer' }}
                onClick={() => setOthers((all) => [...all, { label: '', url: '' }])}
              >
                <Icon name="plus" size={12} /> Other
              </button>
            </div>
          )}
        </div>
      </section>

      <p className="hint">
        These go on your profile and into the messages and applications we prepare for you, so recruiters can find your
        work in one click.
      </p>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
          {busy ? (token.trim() ? 'Checking token with GitHub…' : 'Saving…') : submitLabel}
        </button>
        {onSkip && (
          <button type="button" className="btn btn-ghost btn-lg" onClick={onSkip} disabled={busy}>
            Skip for now
          </button>
        )}
        {onCancel && (
          <button type="button" className="btn btn-ghost btn-lg" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
