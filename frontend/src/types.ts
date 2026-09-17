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
