import { useCallback, useEffect, useMemo, useState } from 'react'
import { accountApi } from '../api/account'
import type { CandidateProfile, ExperienceEntry, ProfileEntry, ProfileVersion } from '../api/v1types'
import Icon from '../ui/Icon'
import { Alert, EmptyState, errorMessage, Loading, useToast } from '../ui/kit'

// Versions: the master profile cut for one kind of role. Pick what each version shows;
// everything still lives once in the master.

type Item = { id: string; label: string; kind: string; children?: Item[] }

const text = (e: ProfileEntry) => (typeof e.text === 'string' ? e.text.replace(/^skill:\s*/i, '').replace(/\.$/, '') : '')

function itemsFrom(profile: CandidateProfile['profile']): { group: string; items: Item[] }[] {
  const bullets = (e: { bullets?: { text: string; fact_id: string }[] }) =>
    (e.bullets ?? []).map((b) => ({ id: b.fact_id, label: b.text, kind: 'achievement' }))
  return [
    {
      group: 'Experience',
      items: (profile.experience ?? []).map((r: ExperienceEntry) => ({
        id: r.fact_id!,
        label: r.title && r.company ? `${r.title} · ${r.company}` : text(r),
        kind: 'experience',
        children: bullets(r),
      })),
    },
    {
      group: 'Projects',
      items: (profile.projects ?? []).map((p) => ({
        id: p.fact_id!,
        label: text(p),
        kind: 'project',
        children: bullets(p as { bullets?: { text: string; fact_id: string }[] }),
      })),
    },
    { group: 'Achievements', items: (profile.achievements ?? []).map((a) => ({ id: a.fact_id!, label: text(a), kind: 'achievement' })) },
    { group: 'Skills', items: (profile.skills ?? []).map((s) => ({ id: s.fact_id!, label: text(s), kind: 'skill' })) },
    { group: 'Certifications', items: (profile.certifications ?? []).map((c) => ({ id: c.fact_id!, label: text(c), kind: 'certification' })) },
  ].filter((g) => g.items.length)
}

export default function VersionsTab() {
  const toast = useToast()
  const [versions, setVersions] = useState<ProfileVersion[] | null>(null)
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [editing, setEditing] = useState<ProfileVersion | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [v, p] = await Promise.all([accountApi.listVersions(), accountApi.getProfile()])
      setVersions(v)
      setProfile(p)
    } catch (err) {
      setError(errorMessage(err, 'Could not load your versions.'))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!versions || !profile) return <Loading label="Loading your versions…" />

  if (editing)
    return (
      <VersionEditor
        profile={profile}
        version={editing === 'new' ? null : editing}
        onDone={async (saved) => {
          setEditing(null)
          if (saved) toast.show(`“${saved}” saved`)
          await load()
        }}
      />
    )

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="row-between">
        <p className="muted small" style={{ maxWidth: 560 }}>
          Your master profile holds everything. A version shows only what fits one kind of role, say Backend or Data,
          and is what we write from when you reach out.
        </p>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setEditing('new')}>
          <Icon name="plus" size={14} />
          New version
        </button>
      </div>
      {versions.length === 0 ? (
        <div className="card">
          <EmptyState
            icon="layers"
            title="No versions yet"
            actions={
              <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
                Create your first version
              </button>
            }
          >
            Applying to two kinds of roles? Make a version for each, and pick the projects and pointers that fit.
          </EmptyState>
        </div>
      ) : (
        <div className="grid grid-2">
          {versions.map((v, i) => (
            <article key={v.id} className={`version-card tone-${['lilac', 'sky', 'butter', 'peach'][i % 4]}`}>
              <div className="row-between">
                <h3 className="dash-card-title" style={{ fontSize: '1.15rem' }}>
                  {v.name}
                </h3>
                <span className="tiny muted">{v.fact_ids.length} items</span>
              </div>
              {v.target_role && <p className="small">For {v.target_role} roles</p>}
              {v.headline && <p className="small muted">“{v.headline}”</p>}
              <div className="row" style={{ gap: 6, marginTop: 'auto' }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(v)}>
                  <Icon name="edit" size={13} />
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={async () => {
                    if (!window.confirm(`Delete the “${v.name}” version? Your master profile stays as it is.`)) return
                    await accountApi.deleteVersion(v.id)
                    load()
                  }}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

function VersionEditor({
  profile,
  version,
  onDone,
}: {
  profile: CandidateProfile
  version: ProfileVersion | null
  onDone: (savedName: string | null) => void
}) {
  const groups = useMemo(() => itemsFrom(profile.profile), [profile])
  const all = useMemo(() => groups.flatMap((g) => g.items.flatMap((i) => [i.id, ...(i.children ?? []).map((c) => c.id)])), [groups])
  const [name, setName] = useState(version?.name ?? '')
  const [role, setRole] = useState(version?.target_role ?? '')
  const [headline, setHeadline] = useState(version?.headline ?? '')
  const [chosen, setChosen] = useState<Set<string>>(() => new Set(version ? version.fact_ids : all))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = (ids: string[], on: boolean) =>
    setChosen((prev) => {
      const next = new Set(prev)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return next
    })

  async function save() {
    if (!name.trim()) {
      setError('Give the version a name, like “Backend”.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await accountApi.saveVersion(
        { name: name.trim(), target_role: role.trim() || null, headline: headline.trim() || null, fact_ids: [...chosen] },
        version?.id,
      )
      onDone(name.trim())
    } catch (err) {
      setError(errorMessage(err, 'Could not save the version.'))
      setBusy(false)
    }
  }

  return (
    <div className="card card-pad-lg form">
      <h2>{version ? `Edit “${version.name}”` : 'New version'}</h2>
      <div className="grid grid-2" style={{ gap: 12 }}>
        <label className="field">
          <span className="field-label">Name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Backend" maxLength={40} />
        </label>
        <label className="field">
          <span className="field-label">
            For roles like<span className="optional">optional</span>
          </span>
          <input className="input" value={role} onChange={(e) => setRole(e.target.value)} placeholder="Backend engineer" maxLength={80} />
        </label>
      </div>
      <label className="field">
        <span className="field-label">
          Headline<span className="optional">optional</span>
        </span>
        <input
          className="input"
          value={headline}
          onChange={(e) => setHeadline(e.target.value)}
          placeholder="Backend engineer who ships payment systems in Go and Postgres"
          maxLength={160}
        />
      </label>

      <div className="row-between">
        <span className="field-label">What this version shows</span>
        <span className="row small" style={{ gap: 12 }}>
          <button type="button" className="link-btn" onClick={() => setChosen(new Set(all))}>
            All
          </button>
          <button type="button" className="link-btn" onClick={() => setChosen(new Set())}>
            None
          </button>
        </span>
      </div>
      {groups.length === 0 && <p className="muted small">Add experience, projects or skills to your profile first.</p>}
      {groups.map((g) => (
        <section key={g.group} className="version-group">
          <h4>{g.group}</h4>
          {g.group === 'Skills' ? (
            <div className="chips-preview">
              {g.items.map((i) => (
                <button
                  key={i.id}
                  type="button"
                  className={`chip ${chosen.has(i.id) ? 'match-chip' : 'chip-outline'}`}
                  style={{ cursor: 'pointer' }}
                  aria-pressed={chosen.has(i.id)}
                  onClick={() => toggle([i.id], !chosen.has(i.id))}
                >
                  {chosen.has(i.id) && <Icon name="check" size={11} stroke={3} />}
                  {i.label}
                </button>
              ))}
            </div>
          ) : (
            g.items.map((i) => (
              <div key={i.id} className="version-item">
                <label className="row" style={{ gap: 10, flexWrap: 'nowrap', alignItems: 'flex-start' }}>
                  <input
                    type="checkbox"
                    className="check"
                    checked={chosen.has(i.id)}
                    onChange={(e) => toggle([i.id, ...(i.children ?? []).map((c) => c.id)], e.target.checked)}
                  />
                  <strong className="small">{i.label}</strong>
                </label>
                {(i.children ?? []).map((c) => (
                  <label key={c.id} className="row version-child" style={{ gap: 10, flexWrap: 'nowrap', alignItems: 'flex-start' }}>
                    <input type="checkbox" className="check" checked={chosen.has(c.id)} onChange={(e) => toggle([c.id], e.target.checked)} />
                    <span className="small">{c.label}</span>
                  </label>
                ))}
              </div>
            ))
          )}
        </section>
      ))}

      {error && <Alert tone="error">{error}</Alert>}
      <div className="form-actions">
        <button type="button" className="btn btn-primary btn-lg" onClick={save} disabled={busy}>
          {busy ? 'Saving…' : 'Save version'}
        </button>
        <button type="button" className="btn btn-ghost btn-lg" onClick={() => onDone(null)} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  )
}
