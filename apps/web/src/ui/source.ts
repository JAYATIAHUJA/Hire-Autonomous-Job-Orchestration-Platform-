import type { JobContract } from '../types'

// Where a job came from, in words a user recognises.
const NAMES: Record<string, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  remoteok: 'RemoteOK',
  sample: 'Sample data',
}

export function sourceName(job: JobContract): string {
  const key = job.source?.name ?? ''
  return NAMES[key] ?? (key ? key[0].toUpperCase() + key.slice(1) : 'Unknown source')
}

// "the company's careers page" for ATS boards, the job board's name otherwise.
export function sourceLine(job: JobContract): string {
  const key = job.source?.name ?? ''
  if (key === 'greenhouse' || key === 'lever' || key === 'ashby') return `${job.company.name}’s careers page (via ${NAMES[key]})`
  if (key === 'remoteok') return 'RemoteOK job board'
  if (key === 'sample') return 'Sample data for testing — not a real opening'
  return 'Unknown source'
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const ms = Date.now() - new Date(iso).getTime()
  if (Number.isNaN(ms)) return ''
  const mins = Math.round(ms / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}
