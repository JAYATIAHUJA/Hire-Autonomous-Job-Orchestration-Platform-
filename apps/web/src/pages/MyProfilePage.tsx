import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { accountApi } from '../api/account'
import { getProfile as getAnalysis } from '../api/client'
import type { AnswerBank, CandidateProfile, ConsentPurposes, FactProposal, Me, OnlinePresence, PowRun, Preferences, ResumeMerge } from '../api/v1types'
import { useAuth } from '../auth/AuthContext'
import PresenceForm from '../components/PresenceForm'
import ProfileEditor from '../components/ProfileEditor'
import ProfileView from '../components/ProfileView'
import ProgressRing from '../components/ProgressRing'
import VersionsTab from '../components/VersionsTab'
import AnswersStep, { ANSWER_FIELDS, answerLabel } from '../onboarding/AnswersStep'
import FactsStep from '../onboarding/FactsStep'
import PreferencesStep, { BANDS } from '../onboarding/PreferencesStep'
import ResumeStep from '../onboarding/ResumeStep'
import { coverageLabel } from '../onboarding/steps'
import { buildConsentRequest, grantedPurposes, PURPOSES } from '../privacy/consent'
import type { Profile } from '../types'
import Icon, { type IconName } from '../ui/Icon'
import { Alert, EmptyState, errorMessage, initials, Loading, realName, useToast } from '../ui/kit'

type Tab = 'work' | 'links' | 'facts' | 'versions' | 'prefs' | 'answers' | 'privacy'

const TABS: { id: Tab; label: string }[] = [
  { id: 'work', label: 'Proof of work' },
  { id: 'links', label: 'Online profiles' },
  { id: 'facts', label: 'Experience' },
  { id: 'versions', label: 'Versions' },
  { id: 'prefs', label: 'Job preferences' },
  { id: 'answers', label: 'Standard answers' },
  { id: 'privacy', label: 'Privacy' },
]

export default function MyProfilePage() {
  const { auth, setMe } = useAuth()
  const me = auth.status === 'authenticated' ? auth.me : null
  const [params, setParams] = useSearchParams()
  const tab: Tab = TABS.some((t) => t.id === params.get('tab')) ? (params.get('tab') as Tab) : 'work'
  const setTab = (next: Tab) => setParams(next === 'work' ? {} : { tab: next }, { replace: true })
  const [facts, setFacts] = useState<CandidateProfile | null>(null)
  const [presence, setPresence] = useState<OnlinePresence | null>(null)

  useEffect(() => {
    accountApi.getPresence().then(setPresence).catch(() => undefined)
  }, [])

  const loadFacts = useCallback(() => {
    accountApi
      .getProfile()
      .then(setFacts)
      .catch(() => setFacts({ profile: {}, pending_proposals: [], updated_at: null }))
  }, [])

  useEffect(() => {
    loadFacts()
  }, [loadFacts])

  if (!me) return null
  const identity = facts?.profile.identity
  const name = identity?.name?.value || realName(me.display_name) || 'Your profile'
  const location = identity?.location?.value

  return (
    <div className="page profile-layout">
      <aside className="card profile-aside">
        <div className="dash-avatar-wrap" style={{ width: 84, height: 84 }}>
          <span className="dash-avatar" style={{ fontSize: '1.7rem' }}>
            {initials(identity?.name?.value || realName(me.display_name) || me.email)}
          </span>
        </div>
        <h1 className="dash-name" style={{ fontSize: '1.4rem' }}>
          {name}
        </h1>
        <div className="stack small muted" style={{ gap: 6, alignItems: 'center', marginTop: 6 }}>
          {me.email && (
            <span className="row" style={{ gap: 6 }}>
              <Icon name="mail" size={14} />
              {me.email}
            </span>
          )}
          {location && (
            <span className="row" style={{ gap: 6 }}>
              <Icon name="pin" size={14} />
              {location}
            </span>
          )}
        </div>
        {presence && <PresenceLinks presence={presence} onAdd={() => setTab('links')} />}
      </aside>

      <div className="profile-content">
      <div className="tabs" role="tablist" aria-label="Profile sections">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}
            {t.id === 'facts' && (facts?.pending_proposals.length ?? 0) > 0 && (
              <span className="badge badge-accent badge-plain" style={{ marginLeft: 6, height: 20 }}>
                {facts!.pending_proposals.length}
              </span>
            )}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === 'work' && (
          <WorkTab me={me} presence={presence} onOpenLinks={() => setTab('links')} onOpenPrivacy={() => setTab('privacy')} />
        )}
        {tab === 'links' && <LinksTab me={me} onSaved={setPresence} />}
        {tab === 'facts' && <FactsTab me={me} facts={facts} reload={loadFacts} onOpenPrivacy={() => setTab('privacy')} />}
        {tab === 'versions' && <VersionsTab />}
        {tab === 'prefs' && <PrefsTab />}
        {tab === 'answers' && <AnswersTab />}
        {tab === 'privacy' && <PrivacyTab me={me} setMe={setMe} />}
      </div>
      </div>
    </div>
  )
}

/* ---- Proof of work ------------------------------------------------------------------ */

function WorkTab({
  me,
  presence,
  onOpenLinks,
  onOpenPrivacy,
}: {
  me: Me
  presence: OnlinePresence | null
  onOpenLinks: () => void
  onOpenPrivacy: () => void
}) {
  const allowed = grantedPurposes(me.consent).github
  const username = presence?.github_username
  const [run, setRun] = useState<PowRun | null | undefined>(undefined)
  const [analysis, setAnalysis] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    accountApi
      .getLatestPowRun()
      .then(setRun)
      .catch((err) => {
        setError(errorMessage(err, 'Could not load your analysis.'))
        setRun(null)
      })
  }, [])

  // Follow a queued or running analysis until it settles.
  useEffect(() => {
    if (!run || (run.status !== 'queued' && run.status !== 'running')) return
    const id = window.setTimeout(() => {
      accountApi.getPowRun(run.id).then(setRun).catch(() => undefined)
    }, 2000)
    return () => window.clearTimeout(id)
  }, [run])

  useEffect(() => {
    if (run?.status !== 'done' || !run.profile_id) return
    getAnalysis(String(run.profile_id))
      .then(setAnalysis)
      .catch((err) => setError(errorMessage(err, 'Could not load the analysis.')))
  }, [run?.status, run?.profile_id])

  async function start() {
    setError(null)
    try {
      setAnalysis(null)
      setRun(await accountApi.startPowRefresh())
    } catch (err) {
      setError(errorMessage(err, 'Could not start the analysis.'))
    }
  }

  if (!allowed)
    return (
      <div className="card">
        <EmptyState
          icon="lock"
          title="GitHub analysis is switched off"
          actions={
            <button type="button" className="btn btn-primary" onClick={onOpenPrivacy}>
              Change in Privacy
            </button>
          }
        >
          You chose not to let Hire read GitHub. Switch it on to turn your commits into proof of your skills.
        </EmptyState>
      </div>
    )

  if (run === undefined) return <Loading label="Loading your proof of work…" />

  const errorBox = error && (
    <div style={{ marginBottom: 16 }}>
      <Alert tone="error">{error}</Alert>
    </div>
  )

  if (!run) {
    if (!username)
      return (
        <>
          {errorBox}
          <div className="card">
            <EmptyState
              icon="github"
              title="Add your GitHub to build your proof of work"
              actions={
                <button type="button" className="btn btn-primary" onClick={onOpenLinks}>
                  <Icon name="github" size={16} />
                  Add GitHub
                </button>
              }
            >
              We read your repositories, commits and pull requests (read-only) and turn them into a skills profile where
              every claim links to real code.
            </EmptyState>
          </div>
        </>
      )
    return (
      <>
        {errorBox}
        <div className="card">
          <EmptyState
            icon="code"
            title={`Ready to analyse @${username}`}
            actions={
              <button type="button" className="btn btn-primary" onClick={start}>
                Analyse my GitHub
              </button>
            }
          >
            Takes a minute or two. You can leave this page; it keeps running.
            {!presence?.github_token_saved && ' Tip: add a token under Online profiles for a much deeper analysis.'}
          </EmptyState>
        </div>
      </>
    )
  }

  if (run.status === 'queued' || run.status === 'running' || run.status === 'failed') {
    const failed = run.status === 'failed'
    return (
      <>
        {errorBox}
        <div className="card card-pad analysis" style={{ border: '1px solid var(--line)' }}>
          <ProgressRing value={Math.round(run.progress)} />
          <div className="status-body">
            <h3>{failed ? 'The analysis stopped' : run.status === 'queued' ? 'Waiting for a free worker…' : 'Reading your GitHub…'}</h3>
            <p>{failed ? run.error || 'Something went wrong while reading GitHub.' : coverageLabel(run.sample_coverage) ?? 'This usually takes a minute or two.'}</p>
            {failed && (
              <div className="row">
                <button type="button" className="btn btn-primary btn-sm" onClick={start}>
                  <Icon name="refresh" size={14} />
                  Try again
                </button>
              </div>
            )}
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      {errorBox}
      <div className="row-between" style={{ marginBottom: 16 }}>
        <p className="muted small">
          {run.finished_at ? `Analysed ${new Date(run.finished_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}` : 'Analysis ready'}
        </p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={start}>
          <Icon name="refresh" size={14} />
          Run again
        </button>
      </div>
      {analysis ? <ProfileView profile={analysis} /> : !error && <Loading label="Loading analysis…" />}
    </>
  )
}

/* ---- Experience (resume facts, editable) -------------------------------------------- */

function FactsTab({
  me,
  facts,
  reload,
  onOpenPrivacy,
}: {
  me: Me
  facts: CandidateProfile | null
  reload: () => void
  onOpenPrivacy: () => void
}) {
  const allowed = grantedPurposes(me.consent).resume
  const [review, setReview] = useState<FactProposal[] | null>(null)
  const [merge, setMerge] = useState<ResumeMerge | null>(null)
  const [uploading, setUploading] = useState(false)

  if (!facts) return <Loading label="Loading your experience…" />

  const pending = facts.pending_proposals
  if (review || pending.length > 0) {
    return (
      <div className="card card-pad-lg">
        <h2 style={{ marginBottom: 6 }}>Review what we found</h2>
        <p className="muted small" style={{ marginBottom: 20 }}>
          Fix the wording with the pencil, untick what’s wrong. Only what you keep is used on applications.
        </p>
        <FactsStep
          proposals={review ?? pending}
          merge={review ? merge : null}
          onNext={() => {
            setReview(null)
            reload()
          }}
        />
      </div>
    )
  }

  if (uploading)
    return (
      <div className="card card-pad-lg">
        <h2 style={{ marginBottom: 16 }}>Upload a newer resume</h2>
        <ResumeStep
          submitLabel="Read it"
          onUploaded={(result) => {
            setUploading(false)
            setMerge(result)
            setReview(result.proposals)
          }}
          onSkip={() => setUploading(false)}
        />
      </div>
    )

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="row-between">
        <p className="muted small">Your experience, projects and wins, as recruiters see them. Edit anything in place.</p>
        {allowed ? (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setUploading(true)}>
            <Icon name="upload" size={14} />
            Import from resume
          </button>
        ) : (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onOpenPrivacy}>
            Turn on resume import
          </button>
        )}
      </div>
      <ProfileEditor onChange={reload} />
    </div>
  )
}

/* ---- Preferences -------------------------------------------------------------------- */

function PrefsTab() {
  const toast = useToast()
  const [prefs, setPrefs] = useState<Preferences | null | undefined>(undefined)
  const [editing, setEditing] = useState(false)

  const load = useCallback(() => {
    accountApi
      .getPreferences()
      .then((p) => {
        setPrefs(p)
        if (!p) setEditing(true)
      })
      .catch(() => {
        setPrefs(null)
        setEditing(true)
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (prefs === undefined) return <Loading label="Loading your preferences…" />

  if (editing)
    return (
      <div className="card card-pad-lg">
        <h2 style={{ marginBottom: 6 }}>What are you looking for?</h2>
        <p className="muted small" style={{ marginBottom: 20 }}>
          This decides which jobs reach your deck.
        </p>
        <PreferencesStep
          initial={prefs}
          submitLabel="Save preferences"
          onCancel={prefs ? () => setEditing(false) : undefined}
          onSaved={() => {
            setEditing(false)
            toast.show('Preferences saved', 'Your deck will follow them.')
            load()
          }}
        />
      </div>
    )

  const band = BANDS.find((b) => b.value === prefs!.experience_band)?.label
  const salary = prefs!.salary_floor
  return (
    <div className="card card-pad-lg">
      <div className="row-between" style={{ marginBottom: 12 }}>
        <h2>Job preferences</h2>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
          <Icon name="edit" size={14} />
          Edit
        </button>
      </div>
      <dl className="kv">
        <dt>Roles</dt>
        <dd>{prefs!.roles.join(', ')}</dd>
        <dt>Experience</dt>
        <dd>{band ?? <span className="muted">Not set</span>}</dd>
        <dt>Cities</dt>
        <dd>{prefs!.locations.length ? prefs!.locations.join(', ') : <span className="muted">Anywhere</span>}</dd>
        <dt>Remote</dt>
        <dd>{prefs!.remote_ok ? 'Open to remote' : 'Not looking for remote'}</dd>
        <dt>Minimum salary</dt>
        <dd>
          {salary ? `${salary.currency === 'INR' ? '₹' : '$'}${salary.amount.toLocaleString('en-IN')} a year` : <span className="muted">Not set</span>}
        </dd>
        <dt>Deal-breakers</dt>
        <dd>{prefs!.deal_breakers.length ? prefs!.deal_breakers.join(' · ') : <span className="muted">None</span>}</dd>
      </dl>
    </div>
  )
}

/* ---- Standard answers --------------------------------------------------------------- */

function AnswersTab() {
  const toast = useToast()
  const [answers, setAnswers] = useState<AnswerBank | null>(null)
  const [editing, setEditing] = useState(false)

  const load = useCallback(() => {
    accountApi
      .getAnswerBank()
      .then(setAnswers)
      .catch(() => setAnswers({}))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (!answers) return <Loading label="Loading your answers…" />

  if (editing || Object.keys(answers).length === 0)
    return (
      <div className="card card-pad-lg">
        <h2 style={{ marginBottom: 6 }}>Answer the usual questions once</h2>
        <p className="muted small" style={{ marginBottom: 20 }}>
          We prefill these on application forms. You still review every form, and each answer is optional.
        </p>
        <AnswersStep
          submitLabel="Save answers"
          onCancel={Object.keys(answers).length ? () => setEditing(false) : undefined}
          onSaved={() => {
            setEditing(false)
            toast.show('Answers saved')
            load()
          }}
        />
      </div>
    )

  return (
    <div className="card card-pad-lg">
      <div className="row-between" style={{ marginBottom: 12 }}>
        <h2>Standard answers</h2>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
          <Icon name="edit" size={14} />
          Edit
        </button>
      </div>
      <dl className="kv">
        {ANSWER_FIELDS.map((f) => (
          <FragmentRow key={f.key} label={f.label} value={answers[f.key] ? answerLabel(f.key, answers[f.key]) : null} />
        ))}
      </dl>
    </div>
  )
}

function FragmentRow({ label, value }: { label: string; value: string | null }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value ?? <span className="muted">Not answered</span>}</dd>
    </>
  )
}

/* ---- Privacy ------------------------------------------------------------------------ */

function PrivacyTab({ me, setMe }: { me: Me; setMe: (me: Me) => void }) {
  const toast = useToast()
  const current = grantedPurposes(me.consent)
  const [purposes, setPurposes] = useState<ConsentPurposes>(current)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const changed = PURPOSES.some((p) => purposes[p.key] !== current[p.key])

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const consent = await accountApi.recordConsent(await buildConsentRequest(purposes))
      setMe({ ...me, consent })
      toast.show('Privacy choices saved')
    } catch (err) {
      setError(errorMessage(err, 'Could not save your choices.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-pad-lg">
      <h2 style={{ marginBottom: 6 }}>What Hire may use</h2>
      <p className="muted small" style={{ marginBottom: 20 }}>
        Change these any time. Switching something off stops new collection; read the{' '}
        <Link to="/privacy" className="text-link">
          privacy notice
        </Link>{' '}
        for how to have existing data deleted.
      </p>
      <div className="stack" style={{ gap: 10 }}>
        {PURPOSES.map((p) => (
          <label key={p.key} className={`switch-row${purposes[p.key] ? ' on' : ''}`}>
            <span className="switch-row-text">
              <strong>{p.label}</strong>
              <span>{p.detail}</span>
            </span>
            <input
              type="checkbox"
              role="switch"
              className="switch"
              checked={purposes[p.key]}
              onChange={(e) => setPurposes((prev) => ({ ...prev, [p.key]: e.target.checked }))}
            />
          </label>
        ))}
      </div>
      {error && (
        <div style={{ marginTop: 16 }}>
          <Alert tone="error">{error}</Alert>
        </div>
      )}
      <div className="form-actions" style={{ marginTop: 20 }}>
        <button type="button" className="btn btn-primary" onClick={save} disabled={!changed || busy}>
          {busy ? 'Saving…' : 'Save changes'}
        </button>
        {changed && (
          <button type="button" className="btn btn-ghost" onClick={() => setPurposes(current)}>
            Undo
          </button>
        )}
      </div>
    </div>
  )
}

/* ---- Online profiles ---------------------------------------------------------------- */

function LinksTab({ me, onSaved }: { me: Me; onSaved: (p: OnlinePresence) => void }) {
  const toast = useToast()
  return (
    <div className="stack" style={{ gap: 16 }}>
      <p className="muted small">
        Your GitHub, LinkedIn and other profiles. They appear on your profile and in every application and message we
        prepare for you.
      </p>
      <PresenceForm
        githubAllowed={grantedPurposes(me.consent).github}
        submitLabel="Save profiles"
        onSaved={(saved) => {
          onSaved(saved)
          toast.show('Profiles saved', saved.github_token_saved ? 'GitHub token verified and stored encrypted.' : undefined)
        }}
      />
    </div>
  )
}

function PresenceLinks({ presence, onAdd }: { presence: OnlinePresence; onAdd: () => void }) {
  const links: { icon: IconName; label: string; url: string }[] = []
  if (presence.github_username)
    links.push({ icon: 'github', label: `@${presence.github_username}`, url: `https://github.com/${presence.github_username}` })
  if (presence.linkedin) links.push({ icon: 'linkedin', label: 'LinkedIn', url: presence.linkedin })
  if (presence.website) links.push({ icon: 'globe', label: 'Website', url: presence.website })
  if (presence.portfolio) links.push({ icon: 'palette', label: 'Portfolio', url: presence.portfolio })
  for (const o of presence.others) links.push({ icon: 'link', label: o.label, url: o.url })

  return (
    <div className="chips-preview" style={{ marginTop: 12 }}>
      {links.map((l) => (
        <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="chip chip-outline" style={{ textDecoration: 'none' }}>
          <Icon name={l.icon} size={13} />
          {l.label}
        </a>
      ))}
      <button type="button" className="chip chip-outline" style={{ cursor: 'pointer' }} onClick={onAdd}>
        <Icon name={links.length ? 'edit' : 'plus'} size={12} />
        {links.length ? 'Edit links' : 'Add GitHub, LinkedIn…'}
      </button>
    </div>
  )
}
