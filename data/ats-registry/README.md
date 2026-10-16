# ATS registry

The seed list of employers whose **public** Greenhouse, Lever or Ashby job board lists at
least one opening located in India (PLAN.md §5.4, §20 item 6). The job readers crawl these
boards; nothing here is trusted until a probe has seen the board answer.

## Files

| File | What it is | In git |
|---|---|---|
| `candidates.txt` | Hand-written employer names (+ optional slug guesses) | yes |
| `discovered-boards.txt` | `ats:slug` lines seen in the Common Crawl URL index | yes |
| `registry.json` | **The seed**: verified boards with India openings, most openings first | yes |
| `boards-without-india.json` | Boards that exist but list nothing in India today (re-probe later; also useful for remote-global roles) | yes |
| `probe-summary.json` | Counts and hit rates of the last run | yes |
| `.cache/` | Raw probe responses, so re-runs are free and resumable | no |

## Rebuild

```bash
python scripts/ats_registry/discover.py                  # refresh discovered-boards.txt (slow: shared public index)
python scripts/ats_registry/probe.py --boards data/ats-registry/discovered-boards.txt
python scripts/ats_registry/load.py                      # upsert into companies (uses DATABASE_URL)
```

Delete `.cache/` to re-probe from scratch. The probe makes at most 3 requests/second
per ATS host (`--rate`), sends a contact User-Agent, and only calls the documented public
board APIs:

- Greenhouse `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
- Lever `https://api.lever.co/v0/postings/{slug}?mode=json`
- Ashby `https://api.ashbyhq.com/posting-api/job-board/{slug}`

## How a board qualifies

- It answers 200 and lists at least one opening whose location is in India: a whole-word
  match on India or an Indian city/state ("Indiana" does not count), Lever's `country: IN`,
  or Ashby's `addressCountry: India`, including Ashby secondary locations.
- Greenhouse boards report a company name. When we guessed the slug from a name and the
  board belongs to someone else, it is skipped (`name_verified: false` never enters).
  Lever and Ashby don't report one, so name-guessed hits there carry `name_verified: null`,
  and crawl-discovered boards take their name from the board (Greenhouse) or the slug.

## Last run

2026-10-16, 11,768 requests, no errors:

| | Probed | With India openings | Hit rate |
|---|---|---|---|
| Name guesses (`candidates.txt`) | 660 companies | 99 | 15% |
| Crawl-discovered boards | 9,369 slugs | 641 | 6.8% |
| **Registry (merged, deduped)** | | **663 boards** | |

- By ATS: Greenhouse 436, Ashby 208, Lever 19.
- **6,353 India openings** across them. Boards by India openings: 1 → 144, 2–5 → 229,
  6–20 → 216, 21+ → 74.
- A further 6,220 boards are hiring today but not in India; 3,630 of those list remote
  openings (input for the remote-global market).
- Name guesses mostly fail because many Indian employers aren't on these three ATSs.
  The crawl adds boards no one would guess, and its slugs are real by construction.

## Known gaps

- **Lever is under-covered.** Common Crawl barely indexes `jobs.lever.co`, so almost all
  Lever boards come from name guesses. Next source: Lever links on company careers pages.
- Names of crawl-discovered Lever and Ashby boards come from the slug ("Hevodata"), so they need
  a cleanup pass before they appear in the UI.
- Many Indian employers use Workday, Darwinbox, Keka, SmartRecruiters or their own pages.
  They aren't in scope here (PLAN.md Phase 2 adds SmartRecruiters and Workday-CXS readers).
- Openings change daily: the registry says which boards to crawl, not which jobs exist.
