import { useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { ConsentPurposes, Me } from '../api/v1types'
import NoticeContent from '../components/NoticeContent'
import { buildConsentRequest, grantedPurposes, PURPOSES } from '../privacy/consent'

type Props = { me: Me; onAccepted: (me: Me) => void }

export default function ConsentStep({ me, onAccepted }: Props) {
  // Re-consenting to a new version starts from all-off again rather than
  // carrying old answers onto new wording.
  const [purposes, setPurposes] = useState<ConsentPurposes>(() => grantedPurposes(null))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const consent = await accountApi.recordConsent(await buildConsentRequest(purposes))
      onAccepted({ ...me, consent })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save your choices.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="onboarding-step">
      <p className="subtitle">Please read this before we collect anything. It takes about two minutes.</p>
      {/* Focusable so keyboard users can scroll it. */}
      <div className="notice-scroll" tabIndex={0} role="region" aria-label="Privacy notice">
        <NoticeContent headingLevel={3} />
      </div>

      <fieldset className="consent-toggles">
        <legend>Optional uses of your data</legend>
        <p className="hint">Each one is off until you switch it on. You can change these at any time.</p>
        {PURPOSES.map((p) => (
          <label key={p.key} className="consent-toggle">
            <input
              type="checkbox"
              role="switch"
              checked={purposes[p.key]}
              onChange={(e) => setPurposes((prev) => ({ ...prev, [p.key]: e.target.checked }))}
              aria-describedby={`purpose-${p.key}`}
            />
            <span>
              <strong>{p.label}</strong>
              <span id={`purpose-${p.key}`} className="consent-toggle-detail">
                {p.detail}
              </span>
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
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'I have read the notice, continue'}
        </button>
      </div>
    </form>
  )
}
