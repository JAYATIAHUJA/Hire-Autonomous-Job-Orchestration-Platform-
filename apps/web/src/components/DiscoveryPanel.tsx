import { useCallback, useEffect, useRef, useState } from 'react'
import { getDiscovery, requestDiscovery } from '../api/client'
import type { DiscoveryStatus } from '../types'
import Icon from '../ui/Icon'
import { errorMessage } from '../ui/kit'
import { relativeTime } from '../ui/source'

const POLL_MS = 3000

// "Where do these jobs come from?" in one line, with a button to check right now.
// While a check runs it polls and calls onFound when it ends, so lists can reload.
export default function DiscoveryPanel({ onFound, compact }: { onFound?: () => void; compact?: boolean }) {
  const [status, setStatus] = useState<DiscoveryStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const wasRunning = useRef(false)
  const onFoundRef = useRef(onFound)
  onFoundRef.current = onFound

  const load = useCallback(async () => {
    try {
      const next = await getDiscovery()
      setStatus(next)
      const running = Boolean(next.current_run)
      if (wasRunning.current && !running) onFoundRef.current?.()
      wasRunning.current = running
    } catch (err) {
      setError(errorMessage(err, 'Could not check job discovery.'))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!status?.current_run) return
    const id = window.setTimeout(load, POLL_MS)
    return () => window.clearTimeout(id)
  }, [status, load])

  async function checkNow() {
    setError(null)
    try {
      const next = await requestDiscovery()
      wasRunning.current = true
      setStatus(next)
    } catch (err) {
      setError(errorMessage(err, 'Could not start a check.'))
    }
  }

  if (!status) return null
  const run = status.current_run
  const last = status.last_run
  const boards = status.boards_tracked
  const remote = status.by_source.remoteok ?? 0

  return (
    <section className={`discovery${compact ? ' compact' : ''}`} aria-live="polite">
      <div className="discovery-main">
        <span className={`discovery-dot${run ? ' live' : ''}`} aria-hidden="true" />
        <div style={{ flex: 1, minWidth: 0 }}>
          {run ? (
            <strong className="small">
              {run.status === 'requested'
                ? 'Starting a check of company job boards…'
                : `Checking company job boards… ${run.boards_checked} read, ${run.jobs_added} new jobs so far`}
            </strong>
          ) : (
            <strong className="small">
              {status.active_jobs.toLocaleString('en-IN')} live jobs from {status.companies_with_jobs.toLocaleString('en-IN')} companies
            </strong>
          )}
          <div className="tiny muted">
            {last?.finished_at ? `Last checked ${relativeTime(last.finished_at)}` : 'Not checked yet'} · checks every{' '}
            {status.interval_minutes >= 60 ? `${Math.round(status.interval_minutes / 60)} h` : `${status.interval_minutes} min`}
            {' · '}
            <button type="button" className="link-btn tiny" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
              {open ? 'Hide' : 'Where do jobs come from?'}
            </button>
          </div>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={checkNow} disabled={Boolean(run)}>
          <Icon name="refresh" size={14} />
          {run ? 'Checking…' : 'Check now'}
        </button>
      </div>
      {open && (
        <div className="discovery-more small">
          <p>
            We read the official careers pages of <strong>{boards.toLocaleString('en-IN')} companies</strong> hiring in India
            (their public Greenhouse, Lever and Ashby job boards){remote ? <>, plus remote roles from <strong>RemoteOK</strong></> : null}.
            We keep engineering roles in India or remote, drop ones that look like ghost jobs, and close any job its company
            takes down. Every job links to the original posting.
          </p>
          {last && (
            <p className="muted" style={{ marginTop: 6 }}>
              Last check: {last.boards_checked} boards read, {last.jobs_added} new, {last.jobs_closed} closed,{' '}
              {last.ghosts_filtered} ghost jobs filtered out.
            </p>
          )}
        </div>
      )}
      {error && <p className="error-text small" style={{ marginTop: 8 }}>{error}</p>}
    </section>
  )
}
