import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { Bullet, CandidateProfile, ExperienceEntry, FactFields, ProfileEntry } from '../api/v1types'
import Icon from '../ui/Icon'
import { Alert, errorMessage, Loading } from '../ui/kit'

// Edit the profile built from approved facts: fix wording, add the pointers and projects
// the resume missed, delete what is wrong. Every change is one API call and a reload, so
// what is on screen is always what the server has.

type Props = { onChange?: (profile: CandidateProfile) => void }

const text = (e: ProfileEntry) => (typeof e.text === 'string' ? e.text : '')

export default function ProfileEditor({ onChange }: Props) {
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [error, setError] = useState<string | null>(null)
  // A ref, so a parent passing an inline callback does not re-trigger the load.
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const reload = useCallback(async () => {
    try {
      const next = await accountApi.getProfile()
      setProfile(next)
      onChangeRef.current?.(next)
    } catch (err) {
      setError(errorMessage(err, 'Could not load your profile.'))
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  // Run one change, then reload. Errors show at the top; the editor stays usable.
  const run = useCallback(
    async (action: () => Promise<unknown>) => {
      setError(null)
      try {
        await action()
        await reload()
        return true
      } catch (err) {
        setError(errorMessage(err, 'That change was not saved.'))
        return false
      }
    },
    [reload],
  )

  if (!profile) return error ? <Alert tone="error">{error}</Alert> : <Loading label="Loading your profile…" />

  const p = profile.profile
  const edit = (id: string, value: string) => run(() => accountApi.editFact(id, { text: value }))
  const remove = (id: string) => run(() => accountApi.rejectFacts([id]))

  return (
    <div className="stack" style={{ gap: 16 }}>
      {error && <Alert tone="error">{error}</Alert>}

      <Section
        icon="briefcase"
        title="Experience"
        hint="Your roles. Under each, the pointers recruiters read first: what you built and what changed because of it."
        addLabel="Add a role"
        addForm={(done) => <RoleForm onSubmit={async (f) => (await run(() => accountApi.addFact('experience', roleText(f), f))) && done()} />}
      >
        {(p.experience ?? []).map((role) => (
          <RoleCard key={role.fact_id} role={role} run={run} onRemove={() => role.fact_id && remove(role.fact_id)} />
        ))}
      </Section>

      <Section
        icon="code"
        title="Projects"
        hint="One line each: what it is, what you used, and a link if there is one."
        addLabel="Add a project"
        addForm={(done) => (
          <TextAdd
            placeholder="Hire — a swipe-to-apply job app (React, FastAPI, Postgres)"
            onAdd={async (v) => (await run(() => accountApi.addFact('project', v, { name: v.split(/\s[—–:-]\s|:/)[0].trim() }))) && done()}
          />
        )}
      >
        {(p.projects ?? []).map((e) => (
          <ProjectCard key={e.fact_id} project={e as ProjectEntry} run={run} onRemove={() => remove(e.fact_id!)} />
        ))}
      </Section>

      <Section
        icon="sparkle"
        title="Achievements"
        hint="Awards, hackathons, rankings, open-source wins: anything not tied to one job or project."
        addLabel="Add an achievement"
        addForm={(done) => (
          <TextAdd placeholder="Top 1% on LeetCode (rating 2,150)" onAdd={async (v) => (await run(() => accountApi.addFact('achievement', v))) && done()} />
        )}
      >
        {(p.achievements ?? []).map((e) => (
          <EditableRow key={e.fact_id} value={text(e)} multiline onSave={(v) => edit(e.fact_id!, v)} onRemove={() => remove(e.fact_id!)} />
        ))}
      </Section>

      <Section
        icon="zap"
        title="Skills"
        addLabel="Add a skill"
        addForm={(done) => (
          <TextAdd placeholder="Kubernetes" onAdd={async (v) => (await run(() => accountApi.addFact('skill', v, { name: v }))) && done()} />
        )}
      >
        {(p.skills ?? []).length > 0 && (
          <ul className="chip-list" style={{ paddingTop: 4 }}>
            {(p.skills ?? []).map((e) => (
              <li key={e.fact_id} className="chip chip-outline">
                {text(e)}
                <button
                  type="button"
                  className="toast-close"
                  style={{ color: 'var(--muted)', padding: 0 }}
                  aria-label={`Remove ${text(e)}`}
                  onClick={() => remove(e.fact_id!)}
                >
                  <Icon name="x" size={13} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        icon="file"
        title="Education"
        addLabel="Add education"
        addForm={(done) => (
          <TextAdd placeholder="B.Tech, Computer Science — VIT Vellore (2019–2023)" onAdd={async (v) => (await run(() => accountApi.addFact('education', v))) && done()} />
        )}
      >
        {(p.education ?? []).map((e) => (
          <EditableRow key={e.fact_id} value={text(e)} onSave={(v) => edit(e.fact_id!, v)} onRemove={() => remove(e.fact_id!)} />
        ))}
      </Section>

      <Section
        icon="shield"
        title="Certifications"
        addLabel="Add a certification"
        addForm={(done) => (
          <TextAdd placeholder="AWS Certified Developer – Associate (2024)" onAdd={async (v) => (await run(() => accountApi.addFact('certification', v, { name: v }))) && done()} />
        )}
      >
        {(p.certifications ?? []).map((e) => (
          <EditableRow key={e.fact_id} value={text(e)} onSave={(v) => edit(e.fact_id!, v)} onRemove={() => remove(e.fact_id!)} />
        ))}
      </Section>
    </div>
  )
}

/* ---- Sections ----------------------------------------------------------------------- */

function Section({
  icon,
  title,
  hint,
  addLabel,
  addForm,
  children,
}: {
  icon: Parameters<typeof Icon>[0]['name']
  title: string
  hint?: string
  addLabel: string
  addForm: (done: () => void) => React.ReactNode
  children: React.ReactNode
}) {
  const [adding, setAdding] = useState(false)
  const items = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : []
  return (
    <section className="card card-pad" style={{ boxShadow: 'none' }}>
      <div className="row-between" style={{ marginBottom: hint ? 2 : 10 }}>
        <h3 className="row" style={{ gap: 8 }}>
          <Icon name={icon} size={16} />
          {title}
        </h3>
        {!adding && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAdding(true)}>
            <Icon name="plus" size={14} />
            {addLabel}
          </button>
        )}
      </div>
      {hint && <p className="hint" style={{ marginBottom: 10 }}>{hint}</p>}
      {items.length === 0 && !adding && <p className="muted small">Nothing here yet.</p>}
      <div className="stack" style={{ gap: 0 }}>
        {children}
      </div>
      {adding && (
        <div style={{ marginTop: 12 }}>
          {addForm(() => setAdding(false))}
          <button type="button" className="link-btn small" style={{ marginTop: 8 }} onClick={() => setAdding(false)}>
            Cancel
          </button>
        </div>
      )}
    </section>
  )
}

function EditableRow({
  value,
  multiline,
  onSave,
  onRemove,
}: {
  value: string
  multiline?: boolean
  onSave: (v: string) => Promise<boolean>
  onRemove: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [busy, setBusy] = useState(false)

  useEffect(() => setDraft(value), [value])

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!draft.trim() || draft.trim() === value) {
      setEditing(false)
      return
    }
    setBusy(true)
    if (await onSave(draft.trim())) setEditing(false)
    setBusy(false)
  }

  if (editing)
    return (
      <form onSubmit={save} className="stack" style={{ gap: 8, padding: '10px 0', borderBottom: '1px solid var(--line)' }}>
        {multiline ? (
          <textarea className="textarea" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus maxLength={500} />
        ) : (
          <input className="input" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus maxLength={500} />
        )}
        <div className="row" style={{ gap: 6 }}>
          <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setDraft(value)
              setEditing(false)
            }}
          >
            Cancel
          </button>
        </div>
      </form>
    )

  return (
    <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start', padding: '10px 0', borderBottom: '1px solid var(--line)' }}>
      <span style={{ flex: 1, fontSize: '0.9rem', lineHeight: 1.5 }}>{value}</span>
      <button type="button" className="btn btn-ghost btn-icon" style={{ width: 30, height: 30 }} aria-label="Edit" onClick={() => setEditing(true)}>
        <Icon name="edit" size={14} />
      </button>
      <button type="button" className="btn btn-ghost btn-icon" style={{ width: 30, height: 30 }} aria-label="Delete" onClick={onRemove}>
        <Icon name="trash" size={14} />
      </button>
    </div>
  )
}

function TextAdd({ placeholder, onAdd }: { placeholder: string; onAdd: (v: string) => Promise<unknown> }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <form
      className="row"
      style={{ flexWrap: 'nowrap', gap: 8 }}
      onSubmit={async (e) => {
        e.preventDefault()
        if (!value.trim()) return
        setBusy(true)
        await onAdd(value.trim())
        setBusy(false)
        setValue('')
      }}
    >
      <input className="input" value={value} onChange={(e) => setValue(e.target.value)} placeholder={placeholder} autoFocus maxLength={500} />
      <button type="submit" className="btn btn-primary" disabled={busy || !value.trim()}>
        Add
      </button>
    </form>
  )
}

/* ---- Experience --------------------------------------------------------------------- */

type RoleFields = { title: string; company: string; start_date: string; end_date: string }

function roleText(f: FactFields): string {
  const when = [f.start_date, f.end_date || 'present'].filter(Boolean).join(' – ')
  return `${f.title} at ${f.company}${f.start_date ? ` (${when})` : ''}`
}

function RoleForm({ initial, onSubmit, submitLabel = 'Add role' }: { initial?: RoleFields; onSubmit: (f: RoleFields) => Promise<unknown>; submitLabel?: string }) {
  const [f, setF] = useState<RoleFields>(initial ?? { title: '', company: '', start_date: '', end_date: '' })
  const [busy, setBusy] = useState(false)
  const set = (k: keyof RoleFields) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  return (
    <form
      className="stack"
      style={{ gap: 10 }}
      onSubmit={async (e) => {
        e.preventDefault()
        if (!f.title.trim() || !f.company.trim()) return
        setBusy(true)
        await onSubmit({ ...f, title: f.title.trim(), company: f.company.trim() })
        setBusy(false)
      }}
    >
      <div className="grid grid-2" style={{ gap: 10 }}>
        <input className="input" value={f.title} onChange={set('title')} placeholder="Role, e.g. Backend Engineer Intern" aria-label="Role" autoFocus />
        <input className="input" value={f.company} onChange={set('company')} placeholder="Company" aria-label="Company" />
        <input className="input" value={f.start_date} onChange={set('start_date')} placeholder="From, e.g. Jun 2024" aria-label="From" />
        <input className="input" value={f.end_date} onChange={set('end_date')} placeholder="To (empty = present)" aria-label="To" />
      </div>
      <div>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !f.title.trim() || !f.company.trim()}>
          {busy ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )
}

function RoleCard({
  role,
  run,
  onRemove,
}: {
  role: ExperienceEntry
  run: (action: () => Promise<unknown>) => Promise<boolean>
  onRemove: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const id = role.fact_id!
  const heading = role.title && role.company ? `${role.title} · ${role.company}` : text(role)
  const when = [role.start, role.end || (role.start ? 'present' : '')].filter(Boolean).join(' – ')

  return (
    <article style={{ padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
      {editing ? (
        <RoleForm
          submitLabel="Save role"
          initial={{ title: role.title ?? '', company: role.company ?? '', start_date: role.start ?? '', end_date: role.end ?? '' }}
          onSubmit={async (f) => (await run(() => accountApi.editFact(id, { text: roleText(f), structured: f }))) && setEditing(false)}
        />
      ) : (
        <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <strong style={{ fontSize: '0.95rem' }}>{heading}</strong>
            {when && <div className="muted small">{when}</div>}
          </div>
          <button type="button" className="btn btn-ghost btn-icon" style={{ width: 30, height: 30 }} aria-label="Edit role" onClick={() => setEditing(true)}>
            <Icon name="edit" size={14} />
          </button>
          <button type="button" className="btn btn-ghost btn-icon" style={{ width: 30, height: 30 }} aria-label="Delete role" onClick={onRemove}>
            <Icon name="trash" size={14} />
          </button>
        </div>
      )}

      <div style={{ paddingLeft: 14, marginTop: 4, borderLeft: '2px solid var(--line)' }}>
        {(role.bullets ?? []).map((b) => (
          <EditableRow
            key={b.fact_id}
            value={b.text}
            multiline
            onSave={(v) => run(() => accountApi.editFact(b.fact_id, { text: v }))}
            onRemove={() => run(() => accountApi.rejectFacts([b.fact_id]))}
          />
        ))}
        {adding ? (
          <div style={{ paddingTop: 10 }}>
            <TextAdd
              placeholder="Built X with Y, which cut Z by 30%"
              onAdd={async (v) => {
                // An achievement with the role's company and title is filed under that role.
                if (await run(() => accountApi.addFact('achievement', v, { company: role.company ?? null, title: role.title ?? null })))
                  setAdding(false)
              }}
            />
            <button type="button" className="link-btn small" style={{ marginTop: 6 }} onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 6, marginLeft: -10 }} onClick={() => setAdding(true)}>
            <Icon name="plus" size={13} />
            Add a pointer
          </button>
        )}
      </div>
    </article>
  )
}

/* ---- Projects ----------------------------------------------------------------------- */

type ProjectEntry = ProfileEntry & { name?: string | null; url?: string | null; bullets?: Bullet[] }

const projectName = (p: ProjectEntry) => (p.name || text(p).split(/\s[—–:-]\s|:/)[0]).trim()

function ProjectCard({
  project,
  run,
  onRemove,
}: {
  project: ProjectEntry
  run: (action: () => Promise<unknown>) => Promise<boolean>
  onRemove: () => void
}) {
  const id = project.fact_id!
  const [editingLink, setEditingLink] = useState(false)
  const [link, setLink] = useState(project.url ?? '')
  const [adding, setAdding] = useState(false)
  const name = projectName(project)

  async function saveLink(e: FormEvent) {
    e.preventDefault()
    const url = link.trim()
    const clean = url && !/^https?:\/\//i.test(url) ? `https://${url}` : url
    if (await run(() => accountApi.editFact(id, { structured: { url: clean || null, name } }))) setEditingLink(false)
  }

  return (
    <article style={{ padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
      <EditableRow value={text(project)} multiline onSave={(v) => run(() => accountApi.editFact(id, { text: v }))} onRemove={onRemove} />
      <div className="row small" style={{ gap: 8, marginTop: 2 }}>
        <Icon name="link" size={13} />
        {editingLink ? (
          <form onSubmit={saveLink} className="row" style={{ gap: 6, flex: 1, flexWrap: 'nowrap' }}>
            <input
              className="input"
              style={{ minHeight: 34, padding: '6px 10px' }}
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="github.com/you/project or a live demo"
              autoFocus
            />
            <button type="submit" className="btn btn-primary btn-sm">
              Save
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditingLink(false)}>
              Cancel
            </button>
          </form>
        ) : project.url ? (
          <>
            <a href={project.url} target="_blank" rel="noreferrer" className="text-link" style={{ overflowWrap: 'anywhere' }}>
              {project.url.replace(/^https?:\/\//, '')}
            </a>
            <button type="button" className="link-btn tiny" onClick={() => setEditingLink(true)}>
              change
            </button>
          </>
        ) : (
          <button type="button" className="link-btn small" onClick={() => setEditingLink(true)}>
            Add a link (GitHub, demo)
          </button>
        )}
      </div>

      <div style={{ paddingLeft: 14, marginTop: 6, borderLeft: '2px solid var(--line)' }}>
        {(project.bullets ?? []).map((b) => (
          <EditableRow
            key={b.fact_id}
            value={b.text}
            multiline
            onSave={(v) => run(() => accountApi.editFact(b.fact_id, { text: v }))}
            onRemove={() => run(() => accountApi.rejectFacts([b.fact_id]))}
          />
        ))}
        {adding ? (
          <div style={{ paddingTop: 10 }}>
            <TextAdd
              placeholder="What it does, how many use it, what you built"
              onAdd={async (v) => {
                // Pointers file under a project by its name; give the project one first if needed.
                const ok = await run(async () => {
                  if (!project.name) await accountApi.editFact(id, { structured: { name } })
                  await accountApi.addFact('achievement', v, { name })
                })
                if (ok) setAdding(false)
              }}
            />
            <button type="button" className="link-btn small" style={{ marginTop: 6 }} onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 6, marginLeft: -10 }} onClick={() => setAdding(true)}>
            <Icon name="plus" size={13} />
            Add a pointer
          </button>
        )}
      </div>
    </article>
  )
}
