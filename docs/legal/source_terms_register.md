# Source terms register

Gate (claude.md section 4, architecture section 9.8): no `SOURCE_ENABLED_*` flag is turned on, and nothing is fetched from football-data.org or football-data.co.uk, until the entry below for that source is **signed by Divine**. Stage 1 only reads the public terms pages; no data has been fetched from any source.

Personal, non-commercial, probabilities-only use. This is a record of what the sites say, not legal advice.

| Source | Flag | Status | Signed by | Date signed |
|---|---|---|---|---|
| football-data.org (free tier API) | `SOURCE_ENABLED_FDORG` | **OFF, unsigned** | none | none |
| football-data.co.uk (hand-downloaded CSV files) | `SOURCE_ENABLED_FDUK` | **OFF permanently** (ADR-035: never fetched automatically). Hand download and `footy load-csv` is a manual, local step | none | none |
| soccernews.com | none | Outside the system: read only by Divine's Claude Project | not applicable | not applicable |

---

## 1. football-data.org (free tier)

- **Checked:** 2026-10-16 by Claude Code during Stage 1 (Essentials 1, Stage 1 step 2, ADR-032).
- **URLs read:** https://www.football-data.org/pricing , https://www.football-data.org/coverage , https://www.football-data.org/documentation/quickstart . The `/terms` URL answered 404, and `docs.football-data.org/general/v4/overview.html` answered 404.
- **What the pages say**
  - Free plan: "12 competitions", "10 calls/minute", "Scores delayed", "Schedules delayed", "Free Plan is Free Forever."
  - Free competitions: Champions League, Primeira Liga, Premier League, Eredivisie, Bundesliga, Ligue 1, Serie A, La Liga, Championship, Serie A (Brazil), World Cup, European Championships. **The Scottish Premiership is not in the free list**, which matches the design (SPL has no football-data.org code).
  - Coverage page: "Access to data of these leagues & cups is free. Forever."
- **Terms of use:** no usage terms (personal, commercial, caching, redistribution) were found on the pages above. The pricing page says to check the documentation or contact the operator. **Written terms were not located.**
- **Free-history depth: NOT CONFIRMED.** No official page states how many past seasons the free tier returns. A competitor's blog (secondary, commercially interested) says "current season only". Only a real authenticated request for a past season can settle it, and that request is blocked by the legal gate. **If the answer is current-season only**, most teams stay under 10 matches (`INSUFFICIENT_HISTORY`) for weeks and predictions start as teams reach 10 matches (warm-up, ADR-035). Reported to Divine in the Stage 1 tracker entry.
- **Decision recorded:** none yet. `SOURCE_ENABLED_FDORG` stays off.
- **Open for Divine:** (a) email the operator for written terms, or accept personal use under the free plan as stated; (b) after signing, make one authenticated request for a past season to measure the real history depth.

## 2. football-data.co.uk (hand-downloaded CSV files, A-1)

- **Checked:** 2026-10-16 by Claude Code during Stage 1.
- **URL read:** https://www.football-data.co.uk/data.php
- **Quoted clauses (the site's own wording, typo included)**
  - "its use is intended for private individuals only"
  - "NOT commerical or data training products using automated bots/scrapers/AI"
  - "All data provided by Football-Data are made available for the purposes of league match prediction only."
  - For API access the page points to a partner, TheStatsAPI.
- **Coverage:** England (Premiership, Divs 1-3, Conference), Scotland (Premiership, Divs 1-3), Germany, Italy, Spain, France, Netherlands (Eredivisie), Belgium, Portugal (Liga I), Turkey, Greece, plus extra worldwide leagues. Match statistics (shots) since 2000/01 for the major European leagues. The page's own season claims are inconsistent (a 32-season header against 1993/94 in the body). No Champions League.
- **Reading of the clauses:** the stated purpose ("league match prediction") and audience ("private individuals") fit this project's personal, probabilities-only use. The automated-access clause is ambiguous: it may bar all bots or only commercial and training uses. **The page does not address manual downloading by a private individual.** Nothing in the design fetches this site automatically, so the ambiguous clause does not apply to the planned use.
- **Result for A-1 (the Stage 1 check Divine's decision depends on):** the page gives no express permission or prohibition for manual personal downloads. It points toward **path 1 being acceptable** (manual download for personal prediction use, no bot). The wording is not an explicit grant, so the decision is Divine's.
- **Decision recorded:** none yet. `SOURCE_ENABLED_FDUK` stays off permanently; path 1 needs no flag because no HTTP client exists.
- **Open for Divine:** choose A-1 path 1 or path 2 (architecture section 4.3, ADR-035). If path 1, optionally email the site operator to confirm manual personal download in writing and file the reply here.

## 3. soccernews.com

- **Checked:** 2026-10-16 by Claude Code during Stage 1.
- **URL read:** https://www.soccernews.com/terms-and-conditions
- **Quoted clauses:** Section 2.1: "offered to you for your personal and non-commercial use only. Commercial use of this Web Site is strictly prohibited." Section 2.2(d) bars making "copies, modify, reproduce, republish, post, transmit, distribute or alter" the site or its materials. Section 2.3 bars "unlawful or improper use". Automated access, scraping and AI use are not mentioned.
- **Relevance:** this system never reads the site. Only Divine's Claude Project reads it, manually, for his personal use. Nothing from the site is stored in this repo. Outside the system boundary; noted only.
- **Decision recorded:** none needed.

---

## Signature block (to be filled by Divine)

```
Source:        football-data.org
Decision:      [ ] enable   [ ] keep off
Signed by:     ______________   Date: __________
```

```
A-1 path:      [ ] path 1 (hand-download co.uk files)   [ ] path 2 (football-data.org only, drop SPL)
Signed by:     ______________   Date: __________
```
