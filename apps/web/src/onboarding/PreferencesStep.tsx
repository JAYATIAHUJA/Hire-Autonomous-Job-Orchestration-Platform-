import { useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { ExperienceBand, Preferences } from '../api/v1types'
import { splitList } from './steps'

const BANDS: { value: ExperienceBand; label: string }[] = [
  { value: '0-1', label: 'Less than 1 year' },
  { value: '1-3', label: '1 to 3 years' },
  { value: '3-5', label: '3 to 5 years' },
  { value: '5-8', label: '5 to 8 years' },
  { value: '8-12', label: '8 to 12 years' },
  { value: '12+', label: 'More than 12 years' },
]

type Props = { onNext: () => void }

export default function PreferencesStep({ onNext }: Props) {
  const [roles, setRoles] = useState('')
  const [locations, setLocations] = useState('')
  const [remoteOk, setRemoteOk] = useState(false)
  const [band, setBand] = useState<ExperienceBand | ''>('')
  const [salary, setSalary] = useState('')
  const [currency, setCurrency] = useState<'INR' | 'USD'>('INR')
  const [dealBreakers, setDealBreakers] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const roleList = splitList(roles)
    if (roleList.length === 0) {
      setError('Add at least one role you are looking for.')
      return
    }
    const amount = salary.trim() ? Number(salary) : null
    if (amount !== null && (!Number.isFinite(amount) || amount < 0)) {
      setError('Enter the minimum salary as a number, or leave it empty.')
      return
    }
    const prefs: Preferences = {
      roles: roleList,
      locations: splitList(locations),
      remote_ok: remoteOk,
      experience_band: band || null,
      salary_floor: amount === null ? null : { amount, currency, period: 'year' },
      deal_breakers: splitList(dealBreakers),
    }
    setBusy(true)
    setError(null)
    try {
      await accountApi.savePreferences(prefs)
      onNext()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save your preferences.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="onboarding-step connect-form" noValidate>
      <p className="subtitle">This decides which jobs reach your deck. You can change it later.</p>
      <label>
        Roles you want
        <input
          value={roles}
          onChange={(e) => setRoles(e.target.value)}
          placeholder="Backend engineer, SRE"
          required
          aria-describedby="roles-hint"
        />
        <span id="roles-hint" className="hint">
          Separate roles with commas.
        </span>
      </label>
      <label>
        Locations
        <input
          value={locations}
          onChange={(e) => setLocations(e.target.value)}
          placeholder="Bengaluru, Pune"
          autoComplete="off"
        />
      </label>
      <label className="checkbox-label">
        <input type="checkbox" checked={remoteOk} onChange={(e) => setRemoteOk(e.target.checked)} />
        Open to remote roles
      </label>
      <label>
        Experience
        <select value={band} onChange={(e) => setBand(e.target.value as ExperienceBand | '')}>
          <option value="">Choose…</option>
          {BANDS.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
      </label>
      <div className="field-row">
        <label className="field-grow">
          Minimum salary per year <span className="muted">(optional)</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            value={salary}
            onChange={(e) => setSalary(e.target.value)}
            placeholder={currency === 'INR' ? '1800000' : '60000'}
          />
        </label>
        <label>
          Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value as 'INR' | 'USD')}>
            <option value="INR">INR</option>
            <option value="USD">USD</option>
          </select>
        </label>
      </div>
      <label>
        Deal-breakers <span className="muted">(optional)</span>
        <textarea
          rows={3}
          value={dealBreakers}
          onChange={(e) => setDealBreakers(e.target.value)}
          placeholder={'One per line, e.g.\nNo night shifts\nNo bond or service agreement'}
        />
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="step-actions">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Save and continue'}
        </button>
      </div>
    </form>
  )
}
