import { useEffect, useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { AnswerBank } from '../api/v1types'
import { Alert, errorMessage } from '../ui/kit'

type Option = { value: string; label: string }

type Field = { key: string; label: string; hint?: string } & ({ kind: 'choice'; options: Option[] } | { kind: 'text'; placeholder: string })

const YES_NO: Option[] = [
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
]

// Answer-bank keys; the API stores them as-is.
export const ANSWER_FIELDS: Field[] = [
  {
    key: 'notice_period',
    label: 'Notice period',
    kind: 'choice',
    options: [
      { value: 'immediate', label: 'Immediate' },
      { value: '15_days', label: '15 days' },
      { value: '30_days', label: '30 days' },
      { value: '60_days', label: '60 days' },
      { value: '90_days', label: '90 days' },
      { value: 'over_90_days', label: '90+ days' },
    ],
  },
  { key: 'current_ctc', label: 'Current CTC', kind: 'text', placeholder: 'e.g. 12 LPA', hint: 'Only shared on forms that ask for it, after you review them.' },
  { key: 'expected_ctc', label: 'Expected CTC', kind: 'text', placeholder: 'e.g. 18 LPA' },
  { key: 'work_authorisation_india', label: 'Authorised to work in India?', kind: 'choice', options: YES_NO },
  { key: 'needs_sponsorship_abroad', label: 'Need visa sponsorship for roles outside India?', kind: 'choice', options: YES_NO },
  {
    key: 'willing_to_relocate',
    label: 'Willing to relocate?',
    kind: 'choice',
    options: [...YES_NO, { value: 'depends', label: 'Depends' }],
  },
]

export function answerLabel(key: string, value: string): string {
  const field = ANSWER_FIELDS.find((f) => f.key === key)
  if (field?.kind === 'choice') return field.options.find((o) => o.value === value)?.label ?? value
  return value
}

type Props = { onSaved: () => Promise<void> | void; submitLabel?: string; onCancel?: () => void }

export default function AnswersStep({ onSaved, submitLabel = 'Save', onCancel }: Props) {
  const [answers, setAnswers] = useState<AnswerBank>({})
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    accountApi
      .getAnswerBank()
      .then((existing) => {
        if (!cancelled) setAnswers(existing)
      })
      .catch(() => {
        // Start blank; saving still works.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      // Empty answers are not stored.
      const cleaned = Object.fromEntries(Object.entries(answers).filter(([, v]) => v.trim() !== ''))
      await accountApi.saveAnswerBank(cleaned)
      await onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Could not save your answers.'))
      setBusy(false)
    }
  }

  const set = (key: string, value: string) => setAnswers((prev) => ({ ...prev, [key]: value }))

  return (
    <form onSubmit={onSubmit} className="form" aria-busy={!loaded}>
      {ANSWER_FIELDS.map((f) =>
        f.kind === 'choice' ? (
          <div key={f.key} className="field">
            <span className="field-label" id={`ans-${f.key}`}>
              {f.label}
            </span>
            <div className="choice-grid" role="radiogroup" aria-labelledby={`ans-${f.key}`}>
              {f.options.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  role="radio"
                  className="choice"
                  aria-checked={answers[f.key] === o.value}
                  disabled={!loaded}
                  // Tapping the chosen answer again clears it: every answer is optional.
                  onClick={() => set(f.key, answers[f.key] === o.value ? '' : o.value)}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <label key={f.key} className="field">
            <span className="field-label">{f.label}</span>
            <input
              className="input"
              value={answers[f.key] ?? ''}
              onChange={(e) => set(f.key, e.target.value)}
              placeholder={f.placeholder}
              disabled={!loaded}
              autoComplete="off"
            />
            {f.hint && <span className="hint">{f.hint}</span>}
          </label>
        ),
      )}
      {error && <Alert tone="error">{error}</Alert>}
      <div className="form-actions">
        <button type="submit" className="btn btn-accent btn-lg" disabled={busy || !loaded}>
          {busy ? 'Saving…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn btn-ghost btn-lg" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
