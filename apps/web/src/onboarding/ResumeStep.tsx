import { useState, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { FactProposal } from '../api/v1types'

const MAX_BYTES = 5 * 1024 * 1024
const ACCEPT = '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export function resumeFileError(file: File): string | null {
  if (!/\.(pdf|docx)$/i.test(file.name)) return 'Upload a PDF or Word (.docx) file.'
  if (file.size > MAX_BYTES) return 'Your resume must be 5 MB or smaller.'
  return null
}

type Props = { onUploaded: (proposals: FactProposal[]) => void; onSkip: () => void }

export default function ResumeStep({ onUploaded, onSkip }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    const invalid = resumeFileError(file)
    if (invalid) {
      setError(invalid)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await accountApi.uploadResume(file)
      onUploaded(res.proposals)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read your resume.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="onboarding-step connect-form">
      <p className="subtitle">
        We read your resume and suggest facts for your profile. Nothing is added until you approve it on the next
        step.
      </p>
      <label>
        Resume <span className="muted">(PDF or .docx, up to 5 MB)</span>
        <input
          type="file"
          accept={ACCEPT}
          onChange={(e) => {
            const picked = e.target.files?.[0] ?? null
            setFile(picked)
            setError(picked ? resumeFileError(picked) : null)
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? 'resume-error' : undefined}
        />
      </label>
      {error && (
        <p id="resume-error" className="error" role="alert">
          {error}
        </p>
      )}
      <div className="step-actions">
        <button type="submit" disabled={busy || !file || Boolean(error)}>
          {busy ? 'Reading your resume…' : 'Upload and continue'}
        </button>
        <button type="button" className="btn-secondary" onClick={onSkip} disabled={busy}>
          Skip for now
        </button>
      </div>
    </form>
  )
}
