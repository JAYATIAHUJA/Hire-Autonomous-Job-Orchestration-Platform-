import { useState, type DragEvent, type FormEvent } from 'react'
import { accountApi } from '../api/account'
import type { FactProposal, ResumeMerge } from '../api/v1types'
import Icon from '../ui/Icon'
import { Alert, errorMessage } from '../ui/kit'

const MAX_BYTES = 5 * 1024 * 1024
const MAX_FILES = 5
const ACCEPT = '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export function resumeFileError(file: File): string | null {
  if (!/\.(pdf|docx)$/i.test(file.name)) return `${file.name}: upload a PDF or Word (.docx) file.`
  if (file.size > MAX_BYTES) return `${file.name}: must be 5 MB or smaller.`
  return null
}

type Props = { onUploaded: (merge: ResumeMerge) => void; onSkip?: () => void; submitLabel?: string }

// One or several resumes (say, a backend one and a data one). They are read one after
// another and merged: each fact is proposed once, however many resumes mention it.
export default function ResumeStep({ onUploaded, onSkip, submitLabel }: Props) {
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState<number | null>(null) // index being read
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function add(list: FileList | null) {
    if (!list) return
    const next = [...files]
    for (const f of Array.from(list)) {
      if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f)
    }
    setFiles(next.slice(0, MAX_FILES))
    const bad = next.map(resumeFileError).find(Boolean)
    setError(bad ?? (next.length > MAX_FILES ? `Up to ${MAX_FILES} resumes at a time.` : null))
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault()
    setDragging(false)
    add(e.dataTransfer.files)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!files.length || files.some(resumeFileError)) return
    setError(null)
    const proposals: FactProposal[] = []
    const kept = new Map<string, FactProposal>()
    let alreadyHad = 0
    try {
      for (let i = 0; i < files.length; i++) {
        setBusy(i)
        // The first upload replaces leftovers from an earlier session; the rest add to it.
        const res = await accountApi.uploadResume(files[i], i > 0)
        proposals.push(...res.proposals)
        alreadyHad += res.skipped_duplicates ?? 0
        for (const k of res.kept_from_before ?? []) kept.set(k.id, k)
      }
      // A fact one resume left out but another just re-proposed is not "only in older".
      const proposed = new Set(proposals.map((p) => p.text.toLowerCase()))
      onUploaded({
        proposals,
        alreadyHad,
        kept: [...kept.values()].filter((k) => !proposed.has(k.text.toLowerCase())),
        files: files.length,
      })
    } catch (err) {
      setError(errorMessage(err, 'Could not read your resume.'))
    } finally {
      setBusy(null)
    }
  }

  const reading = busy !== null
  return (
    <form onSubmit={onSubmit} className="form">
      <label
        className={`dropzone${dragging ? ' dragging' : ''}${files.length && !error ? ' has-file' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input type="file" accept={ACCEPT} multiple onChange={(e) => add(e.target.files)} aria-describedby={error ? 'resume-error' : undefined} />
        <span className="dropzone-icon">
          <Icon name={files.length ? 'file' : 'upload'} size={20} />
        </span>
        {files.length ? (
          <>
            <strong>
              {files.length} resume{files.length === 1 ? '' : 's'} ready
            </strong>
            <span className="muted small">
              Add another (a different version or an older one) or <span className="text-link">choose more</span>
            </span>
          </>
        ) : (
          <>
            <strong>Drop your resumes here, or click to browse</strong>
            <span className="muted small">One or several · PDF or Word (.docx) · up to 5 MB each</span>
          </>
        )}
      </label>

      {files.length > 0 && (
        <ul className="list-plain card" style={{ padding: '0 14px' }}>
          {files.map((f, i) => (
            <li key={`${f.name}-${f.size}`} className="row" style={{ flexWrap: 'nowrap', gap: 10 }}>
              <Icon name="file" size={15} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
              {busy === i ? (
                <span className="spinner" />
              ) : busy !== null && i < busy ? (
                <Icon name="check" size={15} className="additions" />
              ) : (
                <button
                  type="button"
                  className="btn btn-ghost btn-icon"
                  style={{ width: 28, height: 28 }}
                  aria-label={`Remove ${f.name}`}
                  disabled={reading}
                  onClick={() => setFiles((all) => all.filter((_, j) => j !== i))}
                >
                  <Icon name="x" size={14} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {error && (
        <Alert tone="error" id="resume-error">
          {error}
        </Alert>
      )}
      {reading && (
        <p className="hint" aria-live="polite">
          Reading resume {busy! + 1} of {files.length}… about 15 seconds each.
        </p>
      )}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary btn-lg" disabled={reading || !files.length || Boolean(error)}>
          {reading ? 'Reading…' : submitLabel ?? (files.length > 1 ? `Read ${files.length} resumes` : 'Read my resume')}
        </button>
        {onSkip && (
          <button type="button" className="btn btn-ghost btn-lg" onClick={onSkip} disabled={reading}>
            Skip for now
          </button>
        )}
      </div>
    </form>
  )
}
