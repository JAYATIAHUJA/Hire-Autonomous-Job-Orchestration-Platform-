import { useEffect, useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { AnswerBank } from '../api/v1types'

type Option = { value: string; label: string }

type Field = { key: string; label: string; hint?: string } & ({ kind: 'select'; options: Option[] } | { kind: 'text'; placeholder: string })

const YES_NO: Option[] = [
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
]

// Answer-bank keys; WP6 stores them as-is.
const ANSWER_FIELDS: Field[] = [
  {
    key: 'notice_period',
    label: 'Notice period',
    kind: 'select',
    options: [
      { value: 'immediate', label: 'Can join immediately' },
      { value: '15_days', label: '15 days' },
      { value: '30_days', label: '30 days' },
      { value: '60_days', label: '60 days' },
      { value: '90_days', label: '90 days' },
      { value: 'over_90_days', label: 'More than 90 days' },
    ],
  },
  { key: 'current_ctc', label: 'Current CTC', kind: 'text', placeholder: 'e.g. 12 LPA', hint: 'Only shared on forms that ask for it, after you review them.' },
  { key: 'expected_ctc', label: 'Expected CTC', kind: 'text', placeholder: 'e.g. 18 LPA' },
  {
    key: 'work_authorisation_india',
    label: 'Authorised to work in India?',
    kind: 'select',
    options: YES_NO,
  },
  {
    key: 'needs_sponsorship_abroad',
    label: 'Need visa sponsorship for roles outside India?',
    kind: 'select',
    options: YES_NO,
  },
  {
    key: 'willing_to_relocate',
    label: 'Willing to relocate?',
    kind: 'select',
    options: [...YES_NO, { value: 'depends', label: 'Depends on the role' }],
  },
]

type Props = { onDone: () => Promise<void> }

export default function AnswersStep({ onDone }: Props) {
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
      await onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save your answers.')
      setBusy(false)
    }
  }

  const set = (key: string, value: string) => setAnswers((prev) => ({ ...prev, [key]: value }))

  return (
    <form onSubmit={onSubmit} className="onboarding-step connect-form" aria-busy={!loaded}>
      <p className="subtitle">
        Application forms ask these again and again. Answer once and we fill them in; you still review every form. All
        optional.
      </p>
      {ANSWER_FIELDS.map((f) => (
        <label key={f.key}>
          {f.label}
          {f.kind === 'select' ? (
            <select value={answers[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)} disabled={!loaded}>
              <option value="">Prefer not to say</option>
              {f.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={answers[f.key] ?? ''}
              onChange={(e) => set(f.key, e.target.value)}
              placeholder={f.placeholder}
              disabled={!loaded}
              autoComplete="off"
            />
          )}
          {f.hint && <span className="hint">{f.hint}</span>}
        </label>
      ))}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="step-actions">
        <button type="submit" disabled={busy || !loaded}>
          {busy ? 'Finishing…' : 'Finish and see my deck'}
        </button>
      </div>
    </form>
  )
}
