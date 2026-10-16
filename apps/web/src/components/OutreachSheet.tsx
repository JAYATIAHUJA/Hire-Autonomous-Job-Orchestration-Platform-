import { useCallback, useEffect, useRef, useState } from 'react'
import { accountApi } from '../api/account'
import { draftOutreach, type OutreachDraft } from '../api/client'
import type { ProfileVersion } from '../api/v1types'
import Icon from '../ui/Icon'
import { Alert, errorMessage, useToast } from '../ui/kit'

type Props = { jobId: string; company: string; role: string; onClose: () => void }

// Draft a note to the people hiring, from the user's own profile. The user edits it and
// sends it from their own email or LinkedIn; Hire never sends anything.
export default function OutreachSheet({ jobId, company, role, onClose }: Props) {
  const toast = useToast()
  const [draft, setDraft] = useState<OutreachDraft | null>(null)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [note, setNote] = useState('')
  const [extra, setExtra] = useState('')
  const [tab, setTab] = useState<'email' | 'linkedin'>('email')
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [versions, setVersions] = useState<ProfileVersion[] | null>(null)
  const [versionId, setVersionId] = useState<number | null>(null)

  // Write from the version made for this kind of role, when there is one.
  useEffect(() => {
    accountApi
      .listVersions()
      .then((vs) => {
        const words = role.toLowerCase()
        const fit = vs.find((v) => v.target_role && v.target_role.toLowerCase().split(/\s+/).some((w) => w.length > 3 && words.includes(w)))
        setVersions(vs)
        setVersionId(fit?.id ?? null)
      })
      .catch(() => setVersions([]))
  }, [role])

  const write = useCallback(
    async (mention?: string) => {
      setBusy(true)
      setError(null)
      try {
        const d = await draftOutreach(jobId, mention, versionId)
        setDraft(d)
        setSubject(d.email_subject)
        setBody(d.email_body)
        setNote(d.linkedin_note)
      } catch (err) {
        setError(errorMessage(err, 'Could not write the note.'))
      } finally {
        setBusy(false)
      }
    },
    [jobId, versionId],
  )

  // Write once when the sheet opens (StrictMode runs effects twice in dev; each run is a paid
  // model call). Later drafts only on "Rewrite" or a version change.
  const firstDraft = useRef(false)
  useEffect(() => {
    if (versions === null) return
    if (!firstDraft.current) {
      firstDraft.current = true
      write()
    }
  }, [versions, write])
  const lastVersion = useRef<number | null>(null)
  useEffect(() => {
    if (!firstDraft.current || lastVersion.current === versionId) return
    if (lastVersion.current !== null || versionId !== null) write()
    lastVersion.current = versionId
  }, [versionId, write])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.show(`${what} copied`)
    } catch {
      toast.show('Could not copy', 'Select the text and copy it yourself.')
    }
  }

  const gmail = `https://mail.google.com/mail/?view=cm&fs=1&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <aside className="sheet" role="dialog" aria-modal="true" aria-labelledby="outreach-title" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <div>
            <h2 id="outreach-title">Reach out to {company}</h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              A short note for the {role} role, written from your profile. Edit it, then send it yourself.
            </p>
          </div>
          <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </header>

        <div className="sheet-body">
          {error && <Alert tone="error">{error}</Alert>}

          {versions && versions.length > 0 && (
            <label className="row small" style={{ gap: 8 }}>
              Write from
              <select
                className="select"
                style={{ minHeight: 34, padding: '4px 30px 4px 10px', width: 'auto' }}
                value={versionId ?? ''}
                onChange={(e) => setVersionId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Master profile</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {busy && !draft ? (
            <div className="stack" style={{ gap: 10 }} aria-live="polite">
              <p className="small muted row" style={{ gap: 8 }}>
                <span className="spinner" /> Reading the posting and your profile…
              </p>
              <div className="skeleton" style={{ height: 44 }} />
              <div className="skeleton" style={{ height: 180 }} />
            </div>
          ) : draft ? (
            <>
              <div className="seg" role="tablist" style={{ alignSelf: 'flex-start' }}>
                <button type="button" role="tab" aria-pressed={tab === 'email'} onClick={() => setTab('email')}>
                  Email
                </button>
                <button type="button" role="tab" aria-pressed={tab === 'linkedin'} onClick={() => setTab('linkedin')}>
                  LinkedIn note
                </button>
              </div>

              {tab === 'email' ? (
                <div className="form">
                  <label className="field">
                    <span className="field-label">Subject</span>
                    <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} />
                  </label>
                  <label className="field">
                    <span className="field-label">Message</span>
                    <textarea className="textarea" rows={10} value={body} onChange={(e) => setBody(e.target.value)} />
                    <span className="hint">{body.trim().split(/\s+/).filter(Boolean).length} words</span>
                  </label>
                  <div className="row" style={{ gap: 8 }}>
                    <a href={gmail} target="_blank" rel="noreferrer" className="btn btn-primary">
                      <Icon name="mail" size={15} />
                      Open in Gmail
                    </a>
                    <button type="button" className="btn btn-secondary" onClick={() => copy(`${subject}\n\n${body}`, 'Email')}>
                      Copy
                    </button>
                  </div>
                </div>
              ) : (
                <div className="form">
                  <label className="field">
                    <span className="field-label">Connection note</span>
                    <textarea className="textarea" rows={4} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
                    <span className="hint">{note.length}/300 characters (LinkedIn's limit)</span>
                  </label>
                  <button type="button" className="btn btn-primary" style={{ alignSelf: 'flex-start' }} onClick={() => copy(note, 'Note')}>
                    Copy note
                  </button>
                </div>
              )}

              <section className="source-box">
                <h4 style={{ marginBottom: 8 }}>Who to send it to</h4>
                <p className="small" style={{ color: 'var(--ink-2)' }}>
                  Look for a recruiter, talent partner or the engineering manager for this team. We don’t guess email
                  addresses.
                </p>
                <div className="row" style={{ gap: 8, marginTop: 10 }}>
                  <a href={draft.find_recruiter_url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                    <Icon name="linkedin" size={14} />
                    Find them on LinkedIn
                  </a>
                  {draft.company_careers_url && (
                    <a href={draft.company_careers_url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
                      Job posting
                      <Icon name="external" size={13} />
                    </a>
                  )}
                </div>
              </section>

              {draft.highlights_used.length > 0 && (
                <section>
                  <h4 style={{ marginBottom: 8 }}>Drawn from your profile</h4>
                  <ul className="chip-list">
                    {draft.highlights_used.map((h) => (
                      <li key={h} className="chip match-chip">
                        {h}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <form
                className="row"
                style={{ gap: 8, flexWrap: 'nowrap' }}
                onSubmit={(e) => {
                  e.preventDefault()
                  write(extra)
                }}
              >
                <input
                  className="input"
                  value={extra}
                  onChange={(e) => setExtra(e.target.value)}
                  placeholder="Anything to mention? e.g. I can join in 30 days"
                  maxLength={300}
                />
                <button type="submit" className="btn btn-secondary" disabled={busy}>
                  <Icon name="refresh" size={14} />
                  {busy ? 'Writing…' : 'Rewrite'}
                </button>
              </form>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  )
}
