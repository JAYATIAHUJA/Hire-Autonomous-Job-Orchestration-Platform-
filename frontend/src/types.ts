export type ConfidenceTier = 'Strong' | 'Moderate' | 'Limited'
export type WorkType = 'feature' | 'fix' | 'refactor' | 'test' | 'ci/infra' | 'docs' | 'chore'

export interface Contribution {
  kind: 'commit' | 'pr'
  repo_full_name: string
  url: string
  title: string
  type: WorkType
  date: string | null
  meaningful_additions: number
  meaningful_deletions: number
  files_touched: number
  is_external: boolean
  is_bulk: boolean
  languages: string[]
}

export interface Factor {
  label: string
  met: boolean
  detail: string
}

export interface Skill {
  name: string
  confidence_tier: ConfidenceTier
  lines: number
  project_count: number
  contribution_count: number
  external_pr_count: number
  active_months: number
  first_active: string | null
  last_active: string | null
  factors: Factor[]
  detected_via: string[]
  highlights: Contribution[]
}

export interface Project {
  full_name: string
  url: string
  role: string
  ownership_share: number | null
  is_external: boolean
  contribution_count: number
  meaningful_lines: number
  primary_language: string | null
  last_contribution: string | null
}

export interface WorkMix {
  type: WorkType
  count: number
  lines: number
}

export interface TimelinePoint {
  month: string
  commits: number
}

export interface Profile {
  profile_id: number
  username: string
  analysis_mode: 'full' | 'limited'
  total_projects: number
  total_commits: number
  analyzed_contributions: number
  meaningful_lines: number
  external_merged_prs: number
  languages: string[]
  work_mix: WorkMix[]
  timeline: TimelinePoint[]
  projects: Project[]
  top_contributions: Contribution[]
  skills: Skill[]
}

export interface AnalyzeResponse {
  profile_id: number
  username: string
}

export interface CompanyContract {
  name: string
  domain: string | null
  external_layoff_flag: boolean
}

export interface RoleContract {
  title: string
  location: string
  salary_range: string | null
}

export interface GhostJobMetricsContract {
  ghost_score: number
  risk_band: 'Low' | 'Moderate' | 'High'
  legitimacy_probability: number
  posting_age_days: number
  repost_count: number
}

export interface ParsedRequirementsContract {
  primary_skills: string[]
  experience_level: string
  raw_description_hash: string
}

export interface JobContract {
  job_id: string
  company: CompanyContract
  role: RoleContract
  ghost_job_metrics: GhostJobMetricsContract
  parsed_requirements: ParsedRequirementsContract
  created_at: string
}

export interface JobFeedResponse {
  total: number
  page: number
  limit: number
  min_legitimacy: number
  jobs: JobContract[]
}

export interface ScoreJobRequest {
  posting_age_days: number
  repost_count: number
  raw_description: string
  salary_range?: string | null
  company_name?: string
  company_domain?: string | null
  external_layoff_flag?: boolean | null
}

export interface ScoreJobResponse {
  ghost_score: number
  risk_band: string
  legitimacy_probability: number
  is_ghost: boolean
  posting_age_days: number
  repost_count: number
  features: {
    x_age: number
    x_repost: number
    x_quality: number
    x_salary: number
    x_news: number
    layoff_detail: string | null
    detected_skills: string[]
  }
}

/* ---- Objective 3: swipe deck, signed consent and the pipeline board ---- */

export type PipelineStage = 'applied' | 'interview_scheduled' | 'rejected' | 'skipped'

export interface ConsentReceipt {
  consent_id: string
  subject: string
  employer_name: string
  purpose: string
  granted_at: string
  algorithm: string
  signature: string
  payload: Record<string, unknown>
  verified: boolean
}

export interface PipelineEvent {
  from_stage: string | null
  to_stage: string
  source: 'swipe' | 'imap' | 'manual'
  detail: string | null
  occurred_at: string | null
}

export interface ApplicationCard {
  application_id: string
  job_id: string
  candidate_ref: string
  employer_name: string
  employer_domain: string | null
  role_title: string
  location: string | null
  stage: PipelineStage
  stage_label: string
  swipe_direction: 'left' | 'right'
  created_at: string | null
  updated_at: string | null
  last_event_summary: string | null
  consent: ConsentReceipt | null
  events: PipelineEvent[]
}

export interface SwipeResponse {
  application: ApplicationCard
  consent: ConsentReceipt | null
  already_recorded: boolean
}

export interface BoardColumn {
  stage: PipelineStage
  label: string
  count: number
  cards: ApplicationCard[]
}

export interface BoardResponse {
  candidate_ref: string
  total: number
  columns: BoardColumn[]
}

export interface DeckResponse {
  candidate_ref: string
  total: number
  min_legitimacy: number
  jobs: JobContract[]
}

export interface RecruiterMessage {
  uid: string
  from_address: string
  subject: string
  body: string
}

export interface MailSyncResponse {
  source: 'imap' | 'inline'
  fetched: number
  matched: number
  moved: number
  skipped: number
  errors: string[]
  moves: Record<string, unknown>[]
}
