export type ConfidenceTier = 'Strong' | 'Moderate' | 'Limited'

export interface Evidence {
  repo_full_name: string
  repo_url: string
  commit_count: number
  pr_count: number
  sample_commit_url: string | null
  sample_commit_message: string | null
}

export interface Skill {
  name: string
  confidence_tier: ConfidenceTier
  commit_count: number
  repo_count: number
  pr_count: number
  first_active: string | null
  last_active: string | null
  evidence: Evidence[]
}

export interface Repo {
  full_name: string
  url: string
  primary_language: string | null
  commit_count: number
  additions: number
  deletions: number
  pr_count: number
  last_contribution: string | null
}

export interface TimelinePoint {
  month: string
  commits: number
}

export interface Profile {
  profile_id: number
  username: string
  total_repos: number
  total_commits: number
  total_additions: number
  total_deletions: number
  languages: string[]
  timeline: TimelinePoint[]
  repos: Repo[]
  skills: Skill[]
}

export interface AnalyzeResponse {
  profile_id: number
  username: string
}
