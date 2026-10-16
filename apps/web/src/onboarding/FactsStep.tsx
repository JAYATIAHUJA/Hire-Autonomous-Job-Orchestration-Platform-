import { useMemo, useState } from 'react'
import { accountApi } from '../api/account'
import type { FactProposal, ResumeMerge } from '../api/v1types'
import Icon from '../ui/Icon'
import { Alert, EmptyState, errorMessage } from '../ui/kit'
import { conflictText, defaultSelection, splitProposals } from './steps'

type Props = { proposals: FactProposal[]; onNext: () => void; merge?: ResumeMerge | null }

const KIND_LABELS: Record<string, string> = {
  name: 'Name',
  contact_email: 'Email',
  contact_phone: 'Phone',
  location: 'Location',
  link: 'Link',
  work_authorization: 'Work authorisation',
  language: 'Language',
  education: 'Education',
  experience: 'Experience',
  achievement: 'Achievement',
  project: 'Project',
  skill: 'Skill',
  certification: 'Certification',
}

export const kindLabel = (kind: string) => KIND_LABELS[kind] ?? kind.replace(/_/g, ' ')

function FactMeta({ p }: { p: FactProposal }) {
  return (
    <span className="fact-meta">
      <span className="badge badge-neutral badge-plain">{kindLabel(p.kind)}</span>
      {p.inferred && <span className="badge badge-warn">Our guess — check it</span>}
    </span>
  )
}

export default function FactsStep({ proposals: initial, onNext, merge }: Props) {
  // Local copy: wording fixed here is saved to the server and shown at once.
  const [proposals, setProposals] = useState(initial)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const { additive, conflicts } = useMemo(() => splitProposals(proposals), [proposals])
  const [selected, setSelected] = useState<Set<string>>(() => defaultSelection(additive))
  const [additiveDone, setAdditiveDone] = useState(additive.length === 0)
  const [conflictIndex, setConflictIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err, 'Could not save your choice.'))
    } finally {
      setBusy(false)
    }
  }

  // One batch for every additive fact: ticked ones are approved, unticked ones
  // are discarded.
  const saveAdditive = () =>
    run(async () => {
      const approve = additive.filter((p) => selected.has(p.id)).map((p) => p.id)
      const reject = additive.filter((p) => !selected.has(p.id)).map((p) => p.id)
      if (approve.length) await accountApi.approveFacts(approve)
      if (reject.length) await accountApi.rejectFacts(reject)
      setAdditiveDone(true)
      if (conflicts.length === 0) onNext()
    })

  const saveEdit = (p: FactProposal) =>
    run(async () => {
      const text = draft.trim()
      if (text && text !== p.text) {
        await accountApi.editFact(p.id, { text })
        setProposals((all) => all.map((x) => (x.id === p.id ? { ...x, text, inferred: false } : x)))
      }
      setEditingId(null)
    })

  const resolveConflict = (p: FactProposal, useNew: boolean) =>
    run(async () => {
      await (useNew ? accountApi.approveFacts([p.id]) : accountApi.rejectFacts([p.id]))
      if (conflictIndex + 1 >= conflicts.length) onNext()
      else setConflictIndex((i) => i + 1)
    })

  const summary = merge ? <MergeSummary merge={merge} proposals={proposals} /> : null

  if (proposals.length === 0) {
    return (
      <div className="form">
        {summary}
        <EmptyState icon="file" title="Nothing new in this resume">
          Everything in it is already on your profile, or we could not find facts we were sure about.
        </EmptyState>
        <div className="form-actions">
          <button type="button" className="btn btn-primary btn-lg" onClick={onNext}>
            Continue
          </button>
        </div>
      </div>
    )
  }

  if (!additiveDone) {
    const count = additive.filter((p) => selected.has(p.id)).length
    const allOn = count === additive.length
    return (
      <div className="form">
        {summary}
        <div className="row-between">
          <span className="field-label">
            {additive.length} fact{additive.length === 1 ? '' : 's'} found
          </span>
          <button
            type="button"
            className="link-btn small"
            onClick={() => setSelected(allOn ? new Set() : new Set(additive.map((p) => p.id)))}
          >
            {allOn ? 'Untick all' : 'Tick all'}
          </button>
        </div>
        <div className="card" style={{ overflow: 'hidden' }}>
          {additive.map((p) =>
            editingId === p.id ? (
              <form
                key={p.id}
                className="stack"
                style={{ gap: 8, padding: '14px 16px', borderBottom: '1px solid var(--line)' }}
                onSubmit={(e) => {
                  e.preventDefault()
                  saveEdit(p)
                }}
              >
                <textarea className="textarea" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus maxLength={500} />
                <div className="row" style={{ gap: 6 }}>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
                    Save
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditingId(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div key={p.id} className="fact-row" style={{ cursor: 'default' }}>
                <input
                  type="checkbox"
                  className="check"
                  aria-label={`Keep: ${p.text}`}
                  checked={selected.has(p.id)}
                  onChange={(e) =>
                    setSelected((prev) => {
                      const next = new Set(prev)
                      if (e.target.checked) next.add(p.id)
                      else next.delete(p.id)
                      return next
                    })
                  }
                />
                <span style={{ flex: 1 }}>
                  <span className="fact-text">{p.text}</span>
                  <FactMeta p={p} />
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-icon"
                  style={{ width: 30, height: 30 }}
                  aria-label={`Fix: ${p.text}`}
                  onClick={() => {
                    setDraft(p.text)
                    setEditingId(p.id)
                    // Fixing a fact means you want it: tick it.
                    setSelected((prev) => new Set(prev).add(p.id))
                  }}
                >
                  <Icon name="edit" size={14} />
                </button>
              </div>
            ),
          )}
        </div>
        <p className="hint">
          Tap the pencil to fix the wording. Facts marked “our guess” were not stated directly in your resume, so they
          start unticked. Unticked facts are discarded.
        </p>
        {error && <Alert tone="error">{error}</Alert>}
        <div className="form-actions">
          <button type="button" className="btn btn-primary btn-lg" onClick={saveAdditive} disabled={busy}>
            {busy ? 'Saving…' : count === 0 ? 'Discard all and continue' : `Save ${count} fact${count === 1 ? '' : 's'}`}
          </button>
        </div>
      </div>
    )
  }

  const p = conflicts[conflictIndex]
  return (
    <div className="form">
      <Alert tone="warn">
        Your resume disagrees with your profile. Pick the one that’s right ({conflictIndex + 1} of {conflicts.length}).
      </Alert>
      <div className="compare" aria-live="polite">
        <div className="compare-side">
          <span className="compare-label">In your profile now</span>
          <p>{conflictText(p)}</p>
        </div>
        <div className="compare-side new">
          <span className="compare-label">From your resume</span>
          <p>{p.text}</p>
          <FactMeta p={p} />
        </div>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="form-actions">
        <button type="button" className="btn btn-primary btn-lg" onClick={() => resolveConflict(p, true)} disabled={busy}>
          <Icon name="check" size={16} />
          Use the resume version
        </button>
        <button type="button" className="btn btn-secondary btn-lg" onClick={() => resolveConflict(p, false)} disabled={busy}>
          Keep my profile
        </button>
      </div>
    </div>
  )
}

/* What a (re-)upload changed, before the user reviews it. Facts only an older resume had
   stay in the profile; the user can drop any of them here. */
function MergeSummary({ merge, proposals }: { merge: ResumeMerge; proposals: FactProposal[] }) {
  const [kept, setKept] = useState(merge.kept)
  const [open, setOpen] = useState(false)
  const changed = proposals.filter((p) => p.conflict_with).length
  const fresh = proposals.length - changed

  async function drop(p: FactProposal) {
    await accountApi.rejectFacts([p.id])
    setKept((all) => all.filter((k) => k.id !== p.id))
  }

  return (
    <section className="merge">
      <div className="merge-head">
        <strong className="small">
          {merge.files > 1 ? `${merge.files} resumes read and merged` : 'Resume read'}
        </strong>
      </div>
      <div className="merge-stats">
        <span className="merge-stat tone-mint">
          <b>{fresh}</b> new
        </span>
        {changed > 0 && (
          <span className="merge-stat tone-butter">
            <b>{changed}</b> changed — you choose
          </span>
        )}
        <span className="merge-stat tone-sky">
          <b>{merge.alreadyHad}</b> already in your profile
        </span>
        {kept.length > 0 && (
          <button type="button" className="merge-stat tone-lilac" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <b>{kept.length}</b> only in your older resume — kept
            <Icon name="chevronDown" size={13} />
          </button>
        )}
      </div>
      {open && kept.length > 0 && (
        <ul className="list-plain" style={{ marginTop: 8 }}>
          {kept.map((k) => (
            <li key={k.id} className="row" style={{ flexWrap: 'nowrap', gap: 10 }}>
              <span className="badge badge-neutral badge-plain">{kindLabel(k.kind)}</span>
              <span style={{ flex: 1 }} className="small">
                {k.text}
              </span>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => drop(k)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
