import { useMemo, useState } from 'react'
import { accountApi } from '../api/account'
import type { FactProposal } from '../api/v1types'
import { conflictText, defaultSelection, splitProposals } from './steps'

type Props = { proposals: FactProposal[]; onNext: () => void }

function FactMeta({ p }: { p: FactProposal }) {
  return (
    <span className="fact-meta">
      <span className="chip">{p.kind}</span>
      <span className="muted">from {p.source}</span>
      {p.inferred && <span className="fact-inferred">inferred, review</span>}
    </span>
  )
}

export default function FactsStep({ proposals, onNext }: Props) {
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
      setError(err instanceof Error ? err.message : 'Could not save your choice.')
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

  const resolveConflict = (p: FactProposal, useNew: boolean) =>
    run(async () => {
      await (useNew ? accountApi.approveFacts([p.id]) : accountApi.rejectFacts([p.id]))
      if (conflictIndex + 1 >= conflicts.length) onNext()
      else setConflictIndex((i) => i + 1)
    })

  if (proposals.length === 0) {
    return (
      <div className="onboarding-step">
        <p className="subtitle">We did not find any new facts in your resume.</p>
        <div className="step-actions">
          <button type="button" onClick={onNext}>
            Continue
          </button>
        </div>
      </div>
    )
  }

  if (!additiveDone) {
    const count = additive.filter((p) => selected.has(p.id)).length
    return (
      <div className="onboarding-step">
        <p className="subtitle">
          Untick anything that is wrong. Facts marked <span className="fact-inferred">inferred, review</span> were not
          stated directly in your resume, so they start unticked.
        </p>
        <fieldset className="fact-list">
          <legend>New facts from your resume ({additive.length})</legend>
          {additive.map((p) => (
            <label key={p.id} className="fact-item">
              <input
                type="checkbox"
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
              <span>
                <span className="fact-text">{p.text}</span>
                <FactMeta p={p} />
              </span>
            </label>
          ))}
        </fieldset>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="step-actions">
          <button type="button" onClick={saveAdditive} disabled={busy}>
            {busy ? 'Saving…' : count === 0 ? 'Discard all and continue' : `Approve ${count} ${count === 1 ? 'fact' : 'facts'}`}
          </button>
        </div>
        {count < additive.length && <p className="hint">Unticked facts are discarded.</p>}
      </div>
    )
  }

  const p = conflicts[conflictIndex]
  return (
    <div className="onboarding-step">
      <p className="subtitle">
        Your resume disagrees with your profile. Choose which one is right ({conflictIndex + 1} of {conflicts.length}).
      </p>
      <div className="conflict-card" aria-live="polite">
        <div className="conflict-side">
          <span className="conflict-label">In your profile now</span>
          <p>{conflictText(p)}</p>
        </div>
        <div className="conflict-side conflict-new">
          <span className="conflict-label">From your resume</span>
          <p>{p.text}</p>
          <FactMeta p={p} />
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="step-actions">
        <button type="button" onClick={() => resolveConflict(p, true)} disabled={busy}>
          Use the resume version
        </button>
        <button type="button" className="btn-secondary" onClick={() => resolveConflict(p, false)} disabled={busy}>
          Keep my profile
        </button>
      </div>
    </div>
  )
}
