# Executive Summary  
The research uncovered many tools for **developer analytics** but none directly build a skill profile from GitHub commits. Most existing products (Waydev, LinearB, GitPrime/Pluralsight Flow, CodeScene, Graphite, GitMe, etc.) target engineering managers to measure team productivity or code review efficiency. They collect GitHub metadata (commits, PRs, reviews, code churn, etc.) and present dashboards and scores, but emphasize delivery metrics (like DORA) rather than individual skills. Open-source projects exist (e.g. Julia Shtal’s *Personal Developer Analytics* for DORA/SPACE metrics) and research frameworks (DORA, SPACE, DX Core 4). However, few systems turn a developer’s GitHub history into **“proof-of-work” evidence**. 

Existing systems often use **misleading activity counts**. For example, engineering best practices explicitly caution that raw counts of lines of code or commits encourage gaming and say *commit count/lines* are “misleading” productivity metrics. Similarly, PR counts and basic activity rates are considered *“misleading productivity indicators”*. High **code churn** (ratio of deleted to added lines) or many repositories can reflect refactoring or fragmented work and don’t inherently signal greater skill. Conversely, outcomes-oriented measures (DORA metrics) and developer satisfaction cannot be derived from GitHub alone. 

The main gap is a lack of tools that **ground skill claims in concrete GitHub evidence**. HIRE’s focus – an explainable “proof-of-work” portfolio – is unique. We recommend an MVP that fetches a user’s GitHub repos via OAuth, extracts contributions (commits, PRs, issues) per repo, categorizes by language/technology, and highlights notable contributions as evidence. The system should *not* just tally numbers; it should associate each claimed skill with actual repos and commits (with links or excerpts). For example, instead of “React – Advanced”, HIRE would show: React (evidence: contributions in 3 React projects with X PRs, Y lines added, latest activity date, links to key commits).  

In 4–6 weeks for Objective 1, build: **GitHub OAuth → Fetch repos/commits/PRs → Compute basic metrics** (languages, commit count, churn) → **Identify top skills** via simple rules (file types, imports, repo tags) → **Display skill list with evidence** (counts, recency, project names, commit links) → **Evidence-based confidence levels**. This yields a credible proof-of-work profile. Heavier features (LLM-based inference, resume tailoring, RAG) belong to later phases.

# Existing Products  
A number of commercial platforms analyze GitHub activity, but mainly for teams or hiring. Examples include:

- **Waydev** – Engineering analytics for managers. Connects to GitHub/GitLab to show commit counts, code churn, PR cycle time, DORA metrics, etc. Users are engineering leaders tracking teams. It collects commit/PR data and generates dashboards. It produces aggregate scores, but its “predictive delivery” AI is opaque. *Strength:* Rich metrics (DORA, cycle time). *Limitation:* Focuses on teams; its “productivity scores” can mislead individual skill (often criticized for incentivizing raw output).

- **LinearB** – Team efficiency platform linking code to project management. Fetches GitHub and tools like Jira. Calculates DORA/SPACE metrics, PR and code review stats, “flow efficiency” (time in coding vs review). Generates visual reports and alerts. *Strength:* Connects code to business impact. *Limitation:* Emphasis on team KPIs, heavy to set up, no public evidence sharing.

- **GitPrime/Pluralsight Flow** – Focus on developer output. Analyzes commits, PRs, code churn via GitHub/GitLab. Provides leaderboards and flow metrics (like PR size, merge time). *Who uses:* large engineering orgs. *Data collected:* All commit/PR metadata. *Metrics:* DORA, commit/PR stats. *Presentation:* Dashboards for managers. *Score:* no single score, but lots of per-metric charts. *Strength:* Mature product, high-level insights. *Limitation:* Even GitPrime advises caution: raw lines/commits incentivize bad practice.

- **CodeScene** – Code health and delivery analytics. Uses Git to detect hotspots and risks. It includes a “Software Delivery” product that shows per-author stats, code churn, code complexity, team experience. *Who uses:* teams seeking code quality insights. *Data:* repository history. *Metrics:* author contribution patterns, code health scores. *Presentation:* heatmaps, dashboards. *Does well:* linking code risks to contributors. *Limitations:* Focus on team risk; individual skills are secondary.

- **Graphite (by Cursor)** – Developer analytics integrated with GitHub and CI. Emphasizes PR review metrics (response time, size, comments, rejection rate). *Users:* team leads wanting pull-request visibility. *Data:* GitHub PR and review data. *Metrics:* code review latency, review count, merge cycles. *Presentation:* interactive dashboards and recommendations. *Strength:* deep review analytics. *Limitation:* Team-centric, no profile-building for individuals.

- **GitMe Developer Analytics** – New GitHub Marketplace app (31 installs as of listing). Advertised as “AI-measured developer productivity”. It claims to compute “Real Effort Value” for each commit, categorizing changes (feature, bugfix, docs) and tracking code retention. *Users:* engineering managers. *Metrics:* custom effort scores per developer. *Evidence:* shows breakdown of effort categories. *Tech:* AI and GitHub API. *Limitation:* Beta status, opaque scoring.

- **Count.co** – A startup that provides a single “Productivity Score” per developer from GitHub data. It clusters activity patterns and issues performance reports. *Users:* engineering teams. *Data:* GitHub activity (commits, PRs). *Metrics:* “Productivity Score” (details unpublished). *Evidence:* summary dashboards. *Strength:* Attempts to simplify metrics. *Limitation:* Proprietary, not transparent; such single-score metrics are viewed skeptically by practitioners.

- **Lemma (Skills Passport)** – A public platform (open to individuals) to build **verified skill profiles**. Users aggregate evidence (GitHub repos, certifications, peer endorsements) into a “skill passport”. It shows each skill with a trust “SCI score” and links to proofs (code commits, course completions). *Problem:* credible résumé with proof. *Users:* developers showcasing skills. *Data:* connected GitHub, courses, endorsements. *Metrics:* trust score per skill. *Evidence:* links to external proofs (GitHub repos, videos). *Strength:* Multi-source evidence; emphasizes verification. *Limitation:* Relies on self-collection of evidence; not exclusively code-based; closed platform with few users.

- **Swiftcruit** – An AI-driven jobs platform that includes “verified skill profiles”. It generates profiles via coding challenges tied to actual job requirements. *Users:* jobseekers. *Data:* practice assessment results (not GitHub). *Metrics:* “AI Match” scores for jobs. *Evidence:* performance on role-specific tests. *Strength:* Shows readiness via testing. *Limitation:* It focuses on assessments, not on mining GitHub activity; different use case.

**Comparison Table of Systems:**  

| System / Project      | Problem / Users                                     | Data Collected                  | Key Metrics                         | Skills Inference / Evidence      | Scoring / Ranking           | Tech             | Strengths                                                | Limitations                                             |
|-----------------------|-----------------------------------------------------|---------------------------------|--------------------------------------|----------------------------------|-----------------------------|------------------|----------------------------------------------------------|---------------------------------------------------------|
| **Waydev**            | Dev analytics for engineering teams (managers) | GitHub/GitLab commits, PRs     | Commit frequency, PR cycle time, code churn | No explicit skill inference      | Team/individual dashboards   | Web app, BI tools| Rich insight into team workflows; integrates with Jira   | Lacks transparency on “score”; may discourage devs      |
| **LinearB**           | Team efficiency (dev managers)      | GitHub/GitLab, Jira data       | DORA/SPACE metrics, PR size, lead times | Highlights workflow bottlenecks  | No single score           | SaaS, JS front-end| Integrates code & project mgmt; shows flow efficiency    | Team focus; no public profiles; proprietary models      |
| **Pluralsight Flow**  | Engineering leaders (enterprise)                    | Git hosting data, CI data      | DORA metrics, cycle time, PR stats  | None (aggregate only)            | Team health dashboards       | Proprietary      | Industry-standard; deep historical data                | Expensive; commit/LOC metrics may mislead    |
| **CodeScene**         | Code quality and delivery analytics for teams       | Git repo history, codebase     | Code hotspots, churn, author stats | N/A                              | No singular score        | SaaS + analysis| Detects code risks, team dynamics; open-source tier     | Focus on code hotspots; not resume-centric              |
| **Graphite Insights** | Metrics for code review and dev efficiency (teams)   | GitHub PR & review data        | PR review time, comments/PR, merge cycles | No direct skill mapping         | Dashboards, alerts         | Web platform    | Deep PR/review analytics; integrates CI/CD             | Team-level; requires agent integration                  |
| **GitMe Analytics**   | Dev productivity app (teams)        | GitHub repos                   | “Real Effort Value”, code retention | Auto-categorizes commits (feature/bug) | Developer “effort” score | AI/Cloud        | AI-driven categorization; retention tracking           | New/beta; opaque scoring; likely vendor lock-in         |
| **Count**            | Team productivity scoring (startups)               | GitHub activity                | Custom “Productivity Score”           | N/A                              | Single score per dev      | Cloud SaaS      | Simplifies metrics for managers                        | Opaque, risk of misinterpretation                       |
| **Personal Dev Analytics (OSS)** | Self-hosted productivity metrics (individuals/teams) | GitHub, Git, Jira data         | DORA/SPACE metrics, focus ratio       | N/A (team metrics)             | None                     | Java backend     | Open-source, privacy-focused; customizable           | Installation complexity; not mainstream                 |
| **Lemma Skills Passport** | Verifiable portfolio (jobseekers)     | Linked accounts (GitHub, courses, peers) | Trust/SCI score for skills           | Links each skill to proofs       | Trust score per skill     | Web platform    | Multi-evidence skill verification; user-controlled    | Not GitHub-focused; depends on user-claimed evidence    |
| **DevsProfile** (concept)  | Structured developer portfolios      | User-provided projects/data    | N/A (contextual story)              | User narrative + repo links     | No score                 | Web app         | Emphasizes project context and roles | Manual entry; doesn’t auto-derive from code             |

# Existing Open-Source Projects  
Several community projects attempt to visualize or analyze Git data:

- **Git Insights** – A category on GitHub hosting projects like *personal-developer-analytics*, *gita*, *git-insights*, etc. For example, *personal-developer-analytics* (Julia Shtal) is a self-hosted dashboard computing DORA/SPACE metrics from Git and Jira. These serve teams or individuals wanting self-tracking. 

- **gita** – A local CLI for analyzing multiple repos. It includes DORA/SPACE scores (lead time, cycle time, review time, deployment frequency). It’s open-source (Python) and runs locally.

- **Gitential** – (commercial with free tier) offers Git-based metrics for individuals and teams, focusing on PR review times, commit sizes.

- **codemaat** / **git-of-theseus** – Research tools for computing churn and code evolution from git logs (Academia). Not user-friendly dashboards.

- **Wakatime** – Not GitHub-focused, but tracks coding time across languages/IDs as a “developer portfolio” (time spent coding). It gives language usage pie-charts, but does not analyze code content.

These open solutions illustrate approaches (local analysis, DORA metrics) but again emphasize activity, not contextual skill proofs.

# Academic Research  
Research on developer productivity and skill inference emphasizes **outcomes over raw activity**. Key findings:

- **DORA metrics** (from “Accelerate” and Google research) show that *deployment frequency, lead time for changes, change failure rate, and mean time to restore* correlate with team performance. However, these measure *team delivery*, not individual developer skill. The DX blog notes DORA “excel at measuring delivery performance” but “miss the human experience”. 

- **SPACE Framework** (Microsoft) expands DORA by adding Satisfaction, Performance, Activity, Communication & collaboration, Efficiency/flow. It stresses that *activity metrics (e.g. commits) must be balanced with qualitative measures*. Only some SPACE dimensions (Activity, partially Performance) can be seen in GitHub data (commits/PR frequency, CI success as proxies). Satisfaction and Collaboration require surveys or internal data, outside GitHub’s scope.

- **Anti-patterns:** The DX team explicitly warns that *“lines of code and commit count are particularly misleading”*. Counting PRs or tickets as “productivity” is similarly invalid. Academic critiques likewise advise avoiding simple metrics – e.g. one study on GitHub metrics concluded that *high commit rates often reflect trivial changes, and effective work is hard to quantify by count alone*. 

- **Code Churn and Quality:** High churn (many deletions shortly after adding) is often a sign of rework or technical debt. Tools like SonarQube and CodeClimate compute churn rates to flag issues. But research shows churn must be normalized: large, complex features naturally cause more churn, whereas trivial fixes cause low churn – context matters.

- **Skill inference research:** Academic work is sparse on automatically inferring skills from code. One recent study (“What Public Repositories Reveal”) suggests analyzing commit messages, import statements, and repository topics could predict skills, but results are preliminary. Generally, *prediction of individual expertise from code history is an open research problem*. Industry whitepapers (e.g. DX Core 4 reports) suggest combining quantitative metrics with peer assessment for a fuller view, but automated “expert level” inference from GitHub is not yet validated.

# GitHub API Capabilities  
The GitHub APIs offer rich data, but with limits. Key accessible data and retrieval methods include:

- **Repositories:** Via REST: `GET /users/{username}/repos` (public repos only) or `GET /user/repos` (with OAuth, including private). Data: repo names, descriptions, primary language, stars, forks.

- **Commits:** REST: `GET /repos/{owner}/{repo}/commits` lists commits (paginated). Each commit object includes author, date, message and stats (additions/deletions) in `GET /repos/{owner}/{repo}/commits/{sha}`. GraphQL: commit nodes include `additions`, `deletions`, `changedFiles`. However, identifying *which developer authored* each commit can be tricky if multiple emails or if GitHub user ID is unset.  

- **Pull Requests:** REST: `GET /repos/{owner}/{repo}/pulls` (open PRs) and `GET /repos/{owner}/{repo}/pulls?state=all`. GraphQL: use `search` or query `user(login){ pullRequests(...) }` to get PRs by user. Data: PR title, state, merged status, timestamps.

- **PR Reviews:** REST: `GET /repos/{owner}/{repo}/pulls/{number}/reviews`. GraphQL: each PullRequest node has `reviews` with author and comments. Useful to gauge collaboration but limited to PRs.

- **Issues:** `GET /repos/{owner}/{repo}/issues` (state=all). Issues often equate with bug reports or tasks. A developer’s issue creations or comments can be fetched to gauge community involvement.

- **Languages:** `GET /repos/{owner}/{repo}/languages` returns a breakdown of bytes per language (using GitHub’s Linguist). This covers entire repo, not per user. GraphQL: each Repository has a `languages` connection (but again totals). No direct “lines per language per developer” endpoint exists; one would have to analyze file-by-file history.

- **Contributions (GraphQL):** The `ContributionsCollection` for a user (with a time range) can report totals for commits, PRs, issues, code reviews, and a breakdown by repository. This makes it easy to get counts of each contribution type for the past year. However, it doesn’t yield raw content or metrics like lines changed.

- **Events API:** REST: `GET /users/{username}/events` returns recent public activity events (PushEvent, PullRequestEvent, etc.). *Limits:* up to 300 events, only last ~30 days. Not reliable for long-term history.

- **Repository Stats:** REST: `GET /repos/{owner}/{repo}/stats/contributors` gives each contributor’s weekly additions/deletions/commits for the repo. Useful to attribute added/deleted lines per user in aggregate. *Limitations:* For very large repos (>10k commits), GitHub may return a 202 “pending” or truncated data.

- **Other metadata:** Branches, tags, releases (via REST), stargazers and forks (REST), watchers, topics, license – all accessible.

**Public vs OAuth vs Repo Access:** Without auth, you can only access public repos and public data at 60 requests/hour. With a personal access token (PAT) or OAuth app token (`repo`, `read:user` scopes), you can see private repos and extended info (e.g. full contributors list, emails if permissioned). GitHub’s rate limit is ~5,000 requests/hour for authenticated REST calls. GraphQL has its own points system (around 5,000 points/hour for user tokens). Some data (e.g. a user’s private commit contributions, team membership, or CI logs) require repo-specific access or GitHub App installation.

**What’s Not Available:** The APIs do **not** provide insights like code quality or correctness; they give only metadata. You cannot get raw diff text (only stats) without additional calls. You can’t see how long a developer spent coding, or measure “understanding of system design” from GitHub. And private repo data is inaccessible unless the user explicitly grants access. 

# Developer-Performance Metrics  
**Useful vs Misleading Metrics:** Research and industry caution against naive counting of activity. The DX blog makes it clear: *lines of code and commit counts encourage gaming (verbose commits, trivial edits)* and are “particularly misleading”. Similarly, counting PRs or issues can reward busywork over substance. Key observations:

- **Commit Count:** Measures the number of commits by a user. *What it measures:* raw frequency of commits. *Potential value:* May roughly indicate engagement. *Why misleading:* Developers can create many tiny commits (e.g. one-line fixes) or bulk commits; neither linearly correlates with impact. **Conclusion:** *Avoid using commit count as a skill signal.*

- **Lines of Code:** Measures lines added/deleted. *Value:* In some contexts, more code written suggests productivity. *Misleading:* Can incentivize bloat or ignore refactoring. As noted, LOC is a poor productivity proxy. It fails to account for non-code work (design, reviews) and penalizes deletion/refactoring. **Conclusion:** *Not recommended.*

- **Lines Added / Lines Deleted (Code Churn):** *Value:* A normal amount of churn is expected; excessive churn suggests instability. *Limitations:* High churn might simply mean a large new feature (adding then refining). Per [74], churn is “a key metric tracking code modifications”. But it must be normalized (e.g. by lines of code or over time). Tools often calculate *churn rate = % of a file changed over time*. HIRE’s “deleted/added” ratio is one view of churn. *Use carefully:* as a secondary indicator of code volatility, not a direct skill measure.

- **Pull Requests:** *Value:* Number of PRs opened/merged shows collaboration. *Misleading:* A high PR count could mean many trivial changes or many small projects. [92] notes PR count is also a “misleading productivity indicator.” PR success rate or time-to-merge might hint at quality and efficiency, but context matters (project rules, team size). 

- **PR Reviews:** Being active in reviewing others’ code suggests collaboration and expertise. Counting review comments or approvals can indicate willingness to mentor. *Limitations:* Volume of reviews depends on team culture and permission; a contributor may not have rights to review, etc. But reviewing is positive evidence of involvement.

- **Issues Filed:** Reporting bugs or suggesting features indicates project engagement. Could hint at problem-solving and communication. But raw issue count is again noisy.

- **Repos/Projects Contributed To:** *Value:* More repositories (especially diverse) suggests breadth. *Misleading:* Many repos might be forks or clones with trivial changes.

- **Activity Frequency:** Commits or PRs per week. *Value:* Shows consistency. *Limitation:* A burst of activity around one project versus sporadic contributions to many.

- **Programming Languages Used:** *Value:* Indicates technical versatility. If someone has commits in JavaScript, Python, Go, we can infer those skills. This is a useful signal (along with evidence). GitHub’s languages API shows repo languages, but HIRE must attribute usage to the user.

- **Time Span / Recency:** *Value:* Ongoing contributions over years shows sustained engagement and up-to-date knowledge. A gap since last commit reduces confidence.

- **Test/Docs Contributions:** Tags in commit messages (or file paths) could mark test coverage or documentation work. Frequent test authorship hints at quality focus. Hard to extract automatically.

- **Bug vs Feature Fixes:** Some advanced systems categorize commits (as GitMe claims) into bugs vs features. This requires AI/NLP and isn’t directly available from GitHub. If possible, distinguishing feature work (maybe more creative) from bug fixes (maintenance) could add nuance. But this is complex to implement for MVP.

- **Code Longevity (Stability):** The idea of “share of lines surviving over days” is akin to measuring how often one’s code remains intact. In practice, one could track when lines a developer added are deleted later. This is a complex *temporal metric*. No major tool uses it explicitly, but it relates to “code ownership” metrics in literature. HIRE could attempt a simplified version (e.g. of last N commits, what fraction have been modified by others). This might signal maintainability of one’s contributions. However, implementation would be heavy (requiring diff histories) and research shows it’s tricky to weight properly (see AI vs human code survival study). This could be deprioritized in MVP.

**Summary:** Out of these, **meaningful signals** include: languages used, repo involvement, sustained frequency, PR & review activity, and diversity of projects. Metrics to use with caution or avoid as primary signals: raw commit count, LOC, total PR count. Code churn can be an auxiliary signal if presented carefully (e.g. normalized or trend-charted). Every metric should be contextualized: HIRE’s profile must emphasize that these are *evidence facets*, not definitive skill ratings.

# SPACE Framework Analysis  
The SPACE model defines five dimensions of developer productivity. What can GitHub reveal?

- **Satisfaction & Well-being:** Not observable via GitHub. No API returns sentiments or burnout levels. Surveys or private developer feedback would be needed. **HIRE cannot measure this**.

- **Performance:** Refers to outcomes like throughput and impact. GitHub can hint at “throughput” (e.g. PRs merged, features delivered) but not actual impact (did a release succeed?). DORA metrics (lead time, deployment frequency) gauge team performance, but HIRE without CI/CD data or access to deployment info can’t measure them accurately. We could infer some performance aspect via PR merge speed or frequency of public releases (tags), but it’s limited.

- **Activity:** Directly measurable. Commits, PRs, issue comments, reviews – all are GitHub activity. This is the easiest SPACE component to see. However, as noted, “activity” alone is not productivity. HIRE can report on activity level (e.g. commit timeline chart) but must clarify it’s just one view.

- **Communication & Collaboration:** Partially accessible. Pull request comments, review feedback, issue discussions, and contributions to others’ repos indicate collaboration. HIRE could count number of reviews done, discussions in issues, or collaborations across repositories. But it won’t capture Slack messages, meetings, or informal collaboration.

- **Efficiency & Flow:** This includes context-switching and waiting time. GitHub data can approximate some: e.g. time from PR open to first review, or fraction of time in active coding (push events) vs waiting. GraphQL’s `pullRequestReview` and PR timestamps can derive cycle times. But “flow” also involves focus (e.g. working on one task at a time), which GitHub alone cannot show. Some aspects (like average open PRs) may hint at flow issues.

**Inference:** With only public GitHub data, we can observe **Activity** and parts of **Collaboration** (reviews) and maybe proxies for **Performance** (e.g. repository “velocity” if we see project releases). But **Satisfaction** and true **Efficiency** are beyond reach. HIRE should explicitly **not claim to measure** things like creativity, team leadership, or personal well-being. It should position itself as evidence-of-skills and experience — *“here are the projects and commits this developer made”*, rather than a holistic productivity assessment. In particular, it must avoid implying a single “intelligence” or “productivity” score, which would misuse the data (see DX caution against surveillance metrics).

# Proof-of-Work Systems  
A true “proof-of-work” profile would highlight concrete contributions rather than vague skill labels. Very few existing systems do this:

- **GitHub Profile / Contributions Graph:** GitHub itself shows a calendar of contributions and top languages. This is a passive portfolio but lacks detail (no view of what the user actually did).

- **Git-based Resumes:** There are open-source resume generators (e.g. jekyll themes) that pull a user’s README or pinned repos, but these generally require manual curation and don’t analyze content.

- **Developer Stories (Discontinued):** GitHub once had “Developer Story” which allowed listing projects and skills. It auto-imported repos as projects, but it’s no longer available. It was a static snapshot, not an analytical profile.

- **Certifications and Badges:** Systems like LinkedIn Skills, Stack Overflow reputation, or blockchain credential platforms (BadgeChain, Credly) provide proof-of-skill, but are disjoint from GitHub. They don’t analyze code.

- **Open-Source Portfolios:** Some developers maintain personal portfolio sites or blogs linking to their GitHub projects and describing their role. These are manually curated narratives, not automated analytics.

In summary, *proof-of-work* differs from *just showing GitHub*. It means **contextualizing** the work. As one developer wrote: real proof includes shipped products, architecture decisions, code contributions, etc. Listing code alone isn’t enough. For HIRE, this suggests the profile should combine quantitative evidence (repo/commit stats) *with context*: project names, user’s role, and description of contributions (even if auto-generated).

HIRE can transform raw activity into evidence by linking skills to repos and commits. Instead of “React – Advanced,” it could show something like:
```
**React (frontend framework):** Contributed to 3 public React projects (X, Y, Z) via 15 commits over 12 months, including implementing key features (e.g. commit abc123 adding a complex UI component). Evidence: [Repo X · PR #42] [Repo Y · File "Todo.jsx"].
```
This kind of display (names, numbers, and links) is novel. It goes beyond “star count” or “lines of code” by naming the actual artifacts. No major product currently provides exactly this. Lemma’s passport does list repos per skill, but only by user entry. DevsProfile emphasizes narrative questions about projects rather than auto-analysis. 

**Conclusion:** HIRE’s “proof-of-work” approach fills a gap: auto-generating a skill profile grounded in specific GitHub commits and projects, with references. It should clearly differentiate from plain GitHub by emphasizing *why* each project proves a skill (showing commit excerpts, PR links, or summarized impact).

# Code-Analysis Technologies  
The choice between analyzing only metadata vs actual code depends on goals:

- **Approach A (Metadata only):** Use GitHub APIs and statistics (commits, languages, PRs). Pros: Simple, fast, no privacy concerns beyond public data. Cons: Misses nuances (e.g. cannot confirm that a commit import `React` means usage of React beyond file name).

- **Approach B (Repo structure):** Clone repos (public ones) and inspect files. For example, look for import statements (e.g. `import React` or `require('react')`), presence of framework-specific files (e.g. `pom.xml` for Maven, `package.json` for Node), or configuration files. Tools: Tree-sitter parsers for multi-language AST parsing; language-specific static analysis (CodeQL, Semgrep); or simple text search. This can confirm technology usage (e.g. list of unique libraries imported by the developer). It requires more code (cloning, parsing) and some risk (downloading large repos).

- **Approach C (Full static analysis):** Run code quality tools (SonarQube, CodeQL) per repo. Assess complexity, test coverage (if tests present), security issues, style. This yields deeper “quality” signals (e.g. cyclomatic complexity, maintainability index). But it’s very heavy: each language needs a toolchain, plus huge compute and permission issues (private code). For a proof-of-work portfolio, this is likely overkill and could raise privacy flags by storing or scanning code. Also, quality metrics often reflect the project, not the individual’s contribution.

For a student-built MVP, **Approach B** is a middle ground: do minimal code parsing to validate technology mentions. For instance, we could parse the *latest version* of each file changed by the user to see what frameworks it uses. Using **Tree-sitter** (which supports many languages) or **simple regex** on source could identify key imports. Static analysis libraries like CodeQL require writing queries per language, too complex. **AST parsing** might extract function names or class names for deeper insight, but probably not necessary initially.

**Privacy and complexity:** Approach A uses only GitHub-provided metadata, so it’s low-risk. Approach B needs actually cloning repos (public only, since private ones require OAuth file access) and processing files, which is somewhat more time-consuming but still public data. Approach C (source analysis) raises ethical questions – do we want to fetch and inspect all code? For open-source, it’s legal; but best to avoid storing code. Minimally, we could run analysis transiently (clone, parse, discard) and keep only extracted facts (e.g. “this repo imports React and Redux”).

**Recommendation:** For HIRE’s MVP, focus on **metadata + lightweight repository analysis** (Approach A+B). Use GitHub API for high-level stats and maybe spot-check code for technology keywords. Skip heavy static analysis (sonarqube, test coverage) due to complexity and diminishing returns for a resume profile. Emphasize evidences like commit messages or code snippets rather than deep code metrics.

# Skill-Inference Approaches  
Translating GitHub activity into identified skills/technologies can use several strategies:

- **Rule-based:** Define heuristics. E.g., if a user has commits in repositories tagged with “react” or files importing “React”, infer React skill. If `package.json` lists `django`, infer Django. Use file extensions: `.js/.tsx` ➔ JavaScript/TypeScript; presence of `requirements.txt` ➔ Python, etc. This is straightforward and interpretable. It misses subtleties (someone could import React but just modify styling).

- **Statistical/ML:** Train a model on labeled data. For example, given a user’s repository metadata and commit vectors, predict skills. One could embed commit messages and code via doc2vec or code2vec models, then classify. However, *getting labeled data* is hard (you’d need many GitHub profiles with known skill labels). OpenAI’s Codex embeddings might cluster by language, but attribution to developer is tricky. This is ambitious and likely too heavy for an MVP. Also, ML models would require lots of engineering and risk overfitting to quirks of the training set.

- **LLM-based (NLP):** Use a large language model (like GPT) to read README files or source snippets and output technology names or roles. For example, prompt: “List the main frameworks and languages used in this repo.” LLMs can often identify technologies from context. You could feed it text from README or code comments. The downside: LLMs can hallucinate or miss less-documented libraries. They also don’t know *who* made the contributions (need to contextualize around the user’s contributions). Still, for saying “this code uses React and Redux”, an LLM is promising.

- **Hybrid:** Combine rules with ML/LLM. First use deterministic clues (filenames, import regex). For less clear cases, use an LLM to parse file contents. The LLM can double-check the rule results or find additional frameworks not in a static list. Also, the LLM might help group related skills (e.g. “React” and “Redux” often co-occur, so mention both if one found).

Given practicality and transparency, **rule-based + keyword extraction** is a safe starting point. For example: scan the user’s top languages (from GitHub’s languages API) and known frameworks for those languages. Also parse `requirements.txt`, `package.json`, `pom.xml`, etc. Optionally, apply an open-source code search library (like [OpenAI’s `langchain` with code embeddings]) to detect commonly used libraries. LLMs could be valuable for higher-level summary (e.g. summarizing contributions into a sentence), but only after we have a list of probable skills.

We recommend a **hybrid rule-based/LLM** pipeline for HIRE: use rules and pattern matching to identify initial skill list, then possibly refine with a small LLM prompt on the user’s README or code excerpts to catch missed technologies. But do not rely solely on LLM for final claims – always tie back to concrete evidence (specific commits or file changes).

# Skill Confidence Model  
HIRE should avoid an absolute “expert” label and instead express **evidence strength**. A simple model: for each skill, collect *evidence sources* (commits in relevant repos, PRs that touch that tech, etc.), then weigh them by recency and scope. For example:

- **Evidence count:** Number of repositories and number of commits tied to the skill. More projects and PRs raise confidence.
- **Evidence strength:** The size or impact of contributions. A PR that adds 100 LOC vs one that adds 1 LOC could count more. (E.g. use additions+deletions or # files changed as a proxy).
- **Recency:** Recent activity in a skill area should count more than old activity. Decay older evidence or flag only past-3-year contributions.
- **Project diversity:** Evidence from multiple unrelated projects (instead of one personal repo) suggests broader expertise.
- **Consistency:** Ongoing contributions across time (not a one-off).

From these, assign a tier or label (e.g. “Limited Evidence”, “Moderate Evidence”, “Strong Evidence”). For instance:
```
Skill: React  
Evidence: 3 projects (42 commits, latest 2mo ago, 50 PR review comments)  
Confidence: Strong evidence of React experience (active last year, contributions in multiple repos).  
```
We should present numeric counts but translate them into qualitative phrases. For example, an internal rule: if >30 commits across >2 repos and active in last 6 months, label “strong evidence”; if 5–10 commits in 1 repo, “some evidence”.

This model should be transparent: the profile can list the factors (e.g. “#Repos, #Commits, Last Active”). Avoid a single opaque score. The DXI example shows a composite index, but HIRE’s profile is at user-level and should emphasize citations: “X features, Y code reviewed, Z repos.” Possibly use a visual indicator (green/yellow/red) or checkmarks per evidence dimension.

No need for a mathematically precise score unless research justifies it. Instead, show evidence and let the reader (recruiter) judge. The interface could say “Based on {repos, pull requests, recency} we see **strong evidence** that the developer has React experience.” This humility avoids overstating confidence and aligns with “evidence not endorsement.” 

# GitHub API Feasibility  
To build HIRE, key API capabilities are:

- **Repositories:** `GET /users/{user}/repos` (public repos) or `GET /user/repos` (with OAuth) to list repos. This gives repo names and metadata. *Limit:* private repos require `repo` scope and the user must have granted it. 

- **Commits per user:** For each repo, use `GET /repos/{owner}/{repo}/commits?author={username}` to list commits by that user. This yields messages and stats. GraphQL alternative: use `repository(owner,name){ ref(qualifiedName:"refs/heads/main"){ target{ history(author:{email:"user@mail.com"}){ edges{node{ additions deletions}}}}}}` to get commits’ stats. But if the user’s GitHub email isn’t on each commit, filtering by author name/email can miss some commits. We may need to match either the GitHub login or known email addresses. 

- **Changed files and stats:** The commit endpoints return `additions`, `deletions`, and changed files. This lets us compute lines changed by user and code churn per commit. GraphQL’s `Commit` object has `additions`/`deletions`. **Available:** yes with each commit fetch. 

- **Programming Language:** GitHub provides an aggregate language breakdown (`GET /repos/.../languages` or GraphQL `repository.languages`). For per-user, not directly available. We can infer a user’s languages by the top languages of repos they contribute to, or by file extensions in their commits.

- **Contribution history:** GraphQL `user{ contributionsCollection }` can give total commits, PRs, and issues in a time range. The REST Events API (`/users/:username/events`) can give recent events but only past month.

- **Pull Requests and Reviews:** REST `GET /search/issues?q=author:{user}+type:pr+repo:{owner}/{repo}` can find PRs by user. GraphQL can query `user{ pullRequests(...) }`. PR review comments and approvals can be fetched via `GET /repos/{owner}/{repo}/pulls/comments?per_page=...` filtered by user. 

- **Repository Ownership:** You can see if the user is owner (via `GET /user` scopes or repo owner field). For org/team roles, need Org API and appropriate permissions (not needed for MVP).

- **Private Data:** Without OAuth, private repos and their data are inaccessible. With OAuth (scopes: `repo`, `read:user`, possibly `user:email`), the app can fetch a user’s private repo contributions.  

- **Rate Limits:** Unauthenticated REST is 60/hr, authenticated 5,000/hr. GraphQL is ~5,000 points/hr per user. We'll need pagination and careful queries to avoid exhaustion. 

- **Unavailable Data:** GitHub won’t tell us *which lines a user introduced* unless we track history. Code quality metrics (complexity, tests) are not in API. And as noted, anything not stored on GitHub (like local commits not pushed) is beyond reach.

**Summary:** All core data for an Objective 1 profile is available via public APIs with appropriate auth: repos list, commits, diffs, PRs, issues, language tags. OAuth with `repo` scope is essential for private repos. The GraphQL API is powerful for aggregated queries (e.g. getting a user’s total contributions in one request), whereas REST endpoints may require looping through repos. For a single developer’s profile, GraphQL’s nested queries can be efficient. However, REST may suffice for MVP with moderate load.  

# Privacy and Ethics  
Analyzing GitHub data must respect privacy and user consent. By default, HIRE will only fetch data the user explicitly authorizes (via OAuth). Public repo activity is already public; summarizing it is fair use. For private repos, the user must grant scope, and HIRE should clearly state what will be accessed. Ethically, HIRE should treat the extracted data *as personal data*: 

- **Consent:** Only analyze private contributions if the user has explicitly consented via OAuth. Allow revocation at any time (delete stored data).  

- **Data Storage:** Store only what’s necessary: e.g. parsed metrics and evidence links, not raw code. If scraping a private repo’s code, avoid permanently saving code files—keep only the derived insights (language names, import list, diff stats). 

- **Transparency:** Inform the user what will be collected (e.g. “we will list your public/private repos and contributions, languages used, and calculate experience metrics”). Make it easy to delete the profile or disconnect GitHub.

- **No Surveillance:** Emphasize that HIRE shows **evidence, not secrets**. Do not display sensitive info like commit author emails or company-confidential messages. For example, if a commit message contains private info (unlikely as a public commit, but possible in private repos), HIRE should scrub or omit it. 

- **Employer Access:** If the profile is shared with recruiters, ensure the user approves that. The goal is to verify skills, not to act as a tracking service. Any scoring or inference should be justified by visible facts (links to code). 

- **Bias and Misrepresentation:** Ensure the profile does not make claims beyond the data. For example, if a developer’s best work is in closed-source code, HIRE cannot fabricate open-source evidence. It should also not penalize a developer for lacking public activity (just reflect “no evidence yet” rather than implying incompetence).

In short, treat GitHub data with user-centric privacy. The design principle is “nothing hidden, user has ultimate control.” This aligns with insights from the DevsProfile article, which warns *“the goal isn’t to reproduce the company repo, but to describe your work without leaking proprietary details.”* HIRE should similarly let users describe their experience, supplementing public evidence but not exposing anything confidential.

# Technology Recommendations  
For building HIRE’s Objective 1 MVP:

- **GitHub OAuth 2.0:** For user login and permission. Request scopes: `repo` (for full repo read), `read:user` (for profile data), and optionally `user:email` (to match commit authorship if needed). 

- **Backend:** Any language (Node.js, Python, etc.) with GitHub API client. Use GitHub’s GraphQL API for aggregated queries (e.g. contributionsCollection, languages), and REST for commit lists and files. 

- **Data Storage:** A simple database (SQLite or MongoDB) to store user profiles: list of repos, computed skill-evidence tuples. Do not store raw source; only references (URLs, IDs) and metrics. 

- **Code Processing:** For each repo, you might clone it or fetch file contents via API if needed (beware rate limits). Use a parser library (like [tree-sitter](https://tree-sitter.github.io/tree-sitter/) or language-specific parsers) to scan key files for frameworks or imports.

- **Frontend:** A web UI (or static site) showing the profile. Use a framework like React or Vue for dynamic display. The profile page should list skills with evidence widgets (counts, charts, links to GitHub commits/PRs). For styling, use a clean resume-style theme.

- **RAG/Evidence Retrieval:** For Objective 1, skip embedding/LLM. Later, if moving to Objective 2, one could embed textual content (README, commit messages) in a vector DB (e.g. Pinecone) for RAG. But for now, focus on static evidence presentation.

- **Continuous Integration:** Use GitHub Actions or similar to periodically refresh data if needed (e.g. re-fetch metrics weekly).

# Identified Gap  
**Existing Tools** largely serve two use cases: (a) **Team analytics** (Waydev, LinearB, Flow, Graphite) – providing managers with dashboards of aggregated metrics; (b) **Portfolio narratives** (personal websites, Lemma) – letting developers list skills and link evidence, but without automatically analyzing code. There is no mainstream tool that **automatically builds an evidence-backed skills profile from someone’s GitHub activity**. 

**Underserved needs:**  
- Job candidates and recruiters lack an automated, objective **proof-of-work profile** that ties claimed skills to actual code contributions.  
- Existing portfolio builders don’t verify skill levels with data, and developer analytics tools don’t share data with recruiters or candidates.  
- There’s a UX gap: recruiters need concise proof rather than raw GitHub browsing.  

**HIRE’s differentiation:** It will fill this gap by combining the best of both worlds: *developer analytics + personal portfolio*. Specifically, HIRE will:  
1. **Aggregate GitHub evidence** per skill. For example, link React with specific repos, PRs, and commits the user made.  
2. **Present narratives from data:** e.g. “We see you built feature X in project Y (with link), which shows your React expertise.” This goes beyond metrics into story.  
3. **Focus on explainability:** Instead of hidden “productivity score,” HIRE’s profile explicitly shows the data behind each skill claim (matching the recommendation to “explain the work”).  

No existing product packages this. Lemma and Swiftcruit verify skills but via challenges/endorsements. They don’t parse code history. DevsProfile addresses context but relies on manual input. HIRE’s **unique contribution** would be auto-mining GitHub and turning it into recruiter-friendly evidence cards. 

# Proposed HIRE MVP (Objective 1)  
A minimal, impressive MVP should demonstrate: *“Yes, HIRE can turn my GitHub into a credible proof-of-work profile.”* Core components:

1. **GitHub OAuth Login:** Let users authenticate via GitHub. Request permission to read their repos and commits.  

2. **Data Fetch:** Retrieve all accessible repositories (public + authorized private). For each:  
   - **Commit history:** Use the REST API or GraphQL to find commits authored by the user. (If ambiguous, match by email and GitHub username.)  
   - **Pull requests:** List PRs opened by the user in those repos. Also, optionally count PR reviews/comments.  
   - **Languages:** Get the primary languages of each repo from the API, to infer which languages the user has worked in.  

3. **Compute Metrics:** For each repo and overall:  
   - Total commits, additions/deletions, lines changed (via stats).  
   - Code churn rate (e.g. deletions/additions ratio) if desired.  
   - Contributions timeline (commit dates for recency chart).  

4. **Skill Extraction:** Identify a set of candidate skills/technologies. Possible methods:  
   - Aggregate all languages (e.g. JavaScript, Python) from repos where the user contributed.  
   - Scan code or config files for frameworks (e.g. `import React`, `from django` in code, or package files).  
   - Manual mapping for common tech (SQL, AWS, frameworks).  

5. **Evidence Linking:** For each identified skill, gather evidence details:  
   - List repositories associated with that skill.  
   - Count number of commits, PRs in those repos.  
   - Determine “first contribution date” and “most recent contribution date” for recency.  
   - Example snippet or link: highlight a representative commit or PR description.  

6. **Confidence/Evidence Display:** For each skill, present:  
   - **Skill name** (e.g. “Python”).  
   - **Evidence summary:** e.g. “Contributions in 4 projects (35 commits, 12 PRs), active 2018–2026.”  
   - **Links:** e.g. “Top commits: [ProjA: Added feature X], [ProjB: Refactored Y]”.  
   - **Confidence:** Qualitative tag like “strong evidence of experience” (based on thresholds of commits/repos/recency).  

7. **Profile UI:** A webpage or dashboard. Section for each skill with the above info, plus maybe charts or graphs (like a bar chart of commits per skill, or a timeline). Also show basic GitHub stats (total repos, stars, etc.) to provide context. 

8. **Technical Architecture:** Likely a simple web app. For example:  
   - Backend (Node.js/Python) handles OAuth, data fetching, and processing.  
   - Frontend (React/Vue) fetches processed JSON from backend and renders the profile.  
   - Persist results in a lightweight DB for speed (so user doesn’t hit rate limits repeatedly).  

**Scope for 4–6 weeks:**  
This MVP requires mostly back-end data integration and a basic front-end. It does *not* need: LLMs for bullet generation, embedding databases, or deep static code analysis. It focuses on reliable GitHub API use and clear evidence presentation. If time remains, add minor polish: caching, basic style, and allow the user to select which skills to display.

# Future Extensions  
After Objective 1, future work could include: 
- **Resume Bullet Generation (RAG):** Use an LLM with the evidence to craft tailored resume lines. For each skill: retrieve related commit messages or docs (as context) and generate a sentence like “Implemented [feature] in [project], using [skill], improving [result].” Ensure citations. RAG can index code comments or README alongside bullet points. 
- **Skill Validation/Tests:** Integrate with coding assessments (like Swiftcruit) or use GitHub Copilot to suggest coding tasks, but this moves beyond mining history. 
- **Collaboration Metrics:** Add team-based analytics, e.g. determine if the user was a lead (e.g. setting up repos) vs occasional contributor. 
- **Mentorship and Communication:** If integrated with Slack/Discord (future!), gauge community help or code reviews. 
- **Gamification:** Badges for range of languages or consistent activity.

These are secondary to the core evidence profile, which should remain the centerpiece.

**Final Recommendation:** In the next 4–6 weeks, build the **GitHub-to-Evidence pipeline**: authenticate, fetch commit/PR data, infer top languages/technologies, and generate an explainable skills profile UI. Focus on accuracy and clarity of evidence rather than fancy AI scoring. This MVP will convincingly demonstrate HIRE’s concept: turning real commit history into a trustworthy proof-of-work profile.