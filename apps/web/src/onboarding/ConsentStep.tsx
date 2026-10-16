import { useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { ConsentPurposes, Me } from '../api/v1types'
import NoticeContent from '../components/NoticeContent'
import { buildConsentRequest, grantedPurposes, PURPOSES } from '../privacy/consent'
import { Alert, errorMessage } from '../ui/kit'

type Props = { me: Me; onAccepted: (me: Me) => void }

export default function ConsentStep({ me, onAccepted }: Props) {
  // Re-consenting to a new version starts from all-off again rather than
  // carrying old answers onto new wording.
  const [purposes, setPurposes] = useState<ConsentPurposes>(() => grantedPurposes(null))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const anyOn = Object.values(purposes).some(Boolean)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const consent = await accountApi.recordConsent(await buildConsentRequest(purposes))
      onAccepted({ ...me, consent })
    } catch (err) {
      setError(errorMessage(err, 'Could not save your choices.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="form">
      {/* Focusable so keyboard users can scroll it. */}
      <div className="notice-scroll" tabIndex={0} role="region" aria-label="Privacy notice">
        <NoticeContent headingLevel={3} />
      </div>

      <fieldset className="stack" style={{ border: 0, margin: 0, padding: 0, gap: 10 }}>
        <legend className="field-label" style={{ marginBottom: 4 }}>
          What may Hire use?
        </legend>
        <p className="hint" style={{ marginTop: -4, marginBottom: 4 }}>
          Everything starts off. Switch on what you want; you can change this later.
        </p>
        {PURPOSES.map((p) => (
          <label key={p.key} className={`switch-row${purposes[p.key] ? ' on' : ''}`}>
            <span className="switch-row-text">
              <strong>{p.label}</strong>
              <span id={`purpose-${p.key}`}>{p.detail}</span>
            </span>
            <input
              type="checkbox"
              role="switch"
              className="switch"
              checked={purposes[p.key]}
              onChange={(e) => setPurposes((prev) => ({ ...prev, [p.key]: e.target.checked }))}
              aria-describedby={`purpose-${p.key}`}
            />
          </label>
        ))}
      </fieldset>

      {!anyOn && (
        <Alert tone="info">
          With everything off you can still swipe jobs and track applications, but your profile will be empty. GitHub
          and resume are what make your applications stand out.
        </Alert>
      )}
      {error && <Alert tone="error">{error}</Alert>}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
          {busy ? 'Saving…' : 'I’ve read this, continue'}
        </button>
      </div>
    </form>
  )
}
