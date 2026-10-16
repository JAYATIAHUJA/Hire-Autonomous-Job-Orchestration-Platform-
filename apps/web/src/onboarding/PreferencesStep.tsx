import { useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { ExperienceBand, Preferences } from '../api/v1types'
import { Alert, errorMessage } from '../ui/kit'
import { splitList } from './steps'

export const BANDS: { value: ExperienceBand; label: string }[] = [
  { value: '0-1', label: 'Intern / Fresher' },
  { value: '1-3', label: '1–3 years' },
  { value: '3-5', label: '3–5 years' },
  { value: '5-8', label: '5–8 years' },
  { value: '8-12', label: '8–12 years' },
  { value: '12+', label: '12+ years' },
]

const ROLE_IDEAS = ['Backend engineer', 'Frontend engineer', 'Full-stack engineer', 'SDE intern', 'Data engineer', 'DevOps / SRE']

type Props = { onSaved: () => void; initial?: Preferences | null; submitLabel?: string; onCancel?: () => void }

export default function PreferencesStep({ onSaved, initial, submitLabel = 'Save', onCancel }: Props) {
  const [roles, setRoles] = useState(initial?.roles.join(', ') ?? '')
  const [locations, setLocations] = useState(initial?.locations.join(', ') ?? '')
  const [remoteOk, setRemoteOk] = useState(initial?.remote_ok ?? false)
  const [band, setBand] = useState<ExperienceBand | ''>(initial?.experience_band ?? '')
  const [salary, setSalary] = useState(initial?.salary_floor ? String(initial.salary_floor.amount) : '')
  const [currency, setCurrency] = useState<'INR' | 'USD'>(initial?.salary_floor?.currency ?? 'INR')
  const [dealBreakers, setDealBreakers] = useState(initial?.deal_breakers.join('\n') ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const roleList = splitList(roles)

  function addRole(role: string) {
    if (roleList.some((r) => r.toLowerCase() === role.toLowerCase())) return
    setRoles([...roleList, role].join(', '))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
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
      onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Could not save your preferences.'))
    } finally {
      setBusy(false)
    }
  }

  const suggestions = ROLE_IDEAS.filter((r) => !roleList.some((x) => x.toLowerCase() === r.toLowerCase()))

  return (
    <form onSubmit={onSubmit} className="form" noValidate>
      <div className="field">
        <label className="field-label" htmlFor="pref-roles">
          Roles you want
        </label>
        <input
          id="pref-roles"
          className="input"
          value={roles}
          onChange={(e) => setRoles(e.target.value)}
          placeholder="Backend engineer, SRE"
          aria-describedby="roles-hint"
        />
        {suggestions.length > 0 && (
          <div className="chips-preview" id="roles-hint">
            {suggestions.slice(0, 5).map((r) => (
              <button key={r} type="button" className="chip chip-outline" style={{ cursor: 'pointer' }} onClick={() => addRole(r)}>
                + {r}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="field">
        <span className="field-label" id="band-label">
          Experience
        </span>
        <div className="choice-grid" role="radiogroup" aria-labelledby="band-label">
          {BANDS.map((b) => (
            <button
              key={b.value}
              type="button"
              role="radio"
              className="choice"
              aria-checked={band === b.value}
              onClick={() => setBand(band === b.value ? '' : b.value)}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>

      <label className="field">
        <span className="field-label">Cities</span>
        <input
          className="input"
          value={locations}
          onChange={(e) => setLocations(e.target.value)}
          placeholder="Bengaluru, Pune, Hyderabad"
          autoComplete="off"
        />
        <span className="hint">Separate with commas.</span>
      </label>

      <label className={`switch-row${remoteOk ? ' on' : ''}`}>
        <span className="switch-row-text">
          <strong>Open to remote roles</strong>
          <span>Remote jobs are added to your deck wherever the company is based.</span>
        </span>
        <input type="checkbox" role="switch" className="switch" checked={remoteOk} onChange={(e) => setRemoteOk(e.target.checked)} />
      </label>

      <div className="field-row">
        <label className="field">
          <span className="field-label">
            Minimum salary per year<span className="optional">optional</span>
          </span>
          <input
            className="input"
            type="number"
            inputMode="numeric"
            min={0}
            value={salary}
            onChange={(e) => setSalary(e.target.value)}
            placeholder={currency === 'INR' ? '1200000' : '60000'}
          />
        </label>
        <label className="field" style={{ width: 110 }}>
          <span className="field-label">Currency</span>
          <select className="select" value={currency} onChange={(e) => setCurrency(e.target.value as 'INR' | 'USD')}>
            <option value="INR">INR ₹</option>
            <option value="USD">USD $</option>
          </select>
        </label>
      </div>

      <label className="field">
        <span className="field-label">
          Deal-breakers<span className="optional">optional</span>
        </span>
        <textarea
          className="textarea"
          rows={3}
          value={dealBreakers}
          onChange={(e) => setDealBreakers(e.target.value)}
          placeholder={'One per line, e.g.\nNo night shifts\nNo service bond'}
        />
      </label>

      {error && <Alert tone="error">{error}</Alert>}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
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
