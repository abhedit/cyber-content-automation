# Abhedit Content Automation: Status and Next Milestone

_Last updated: 2026-11-17_

> **Scope warning.** This status covers **only what is in this GitHub repository**.
> Your newer local copy (handoff notes, n8n workflow, Facebook publisher) was **not
> available** in the session that wrote this file, so none of it is described or
> changed here. Merge this branch into your local copy and nothing of yours is
> overwritten: every change is a new file, except one line added to
> `requirements.txt` and two lines added to `.gitignore`.

## 1. What exists and how far it has been proven

| Component | Where | State |
|---|---|---|
| RSS research over 4 feeds | `generate_content.py`, `news_sources.txt` | **Implemented and run in GitHub Actions** (commits named "Generate daily content"). |
| Gemini content generation (carousel, LinkedIn, Facebook, Instagram, hashtags, image prompts) | `generate_content.py` | **Implemented, runs live** with the `GEMINI_API_KEY` repo secret. Uses `google-generativeai`, which Google no longer supports. |
| Knowledge base (strategy, universe, sources, platform, decision and output frameworks) | `knowledge/` | Written; loaded into the prompt. |
| **Source-locked package + validation + approval gate** (new) | `content_engine/` | **Implemented and unit-tested (30 tests). Dry-run tested only.** Has not been run against live feeds or Gemini yet. |
| Publishing to Facebook / LinkedIn / Instagram | not in this repo | **Not implemented here.** Your n8n Facebook publisher is outside this repo, so this document cannot confirm it has ever posted live. |
| Carousel image rendering | not implemented | Only text image prompts exist; no PNGs are produced. |
| Scheduling | `.github/workflows/daily-content.yml` | Manual trigger only (`workflow_dispatch`); there is no cron schedule. |
| Reporting / analytics | not implemented | None. |

### Problems found in the current generator (from its last committed output)

Checked against AGENTS.md:

- Slide 5 has **41 words** (limit 30), and slide 6 lacks "Follow Abhedit…".
- `output/hashtags.md` is **empty** (0 of 20).
- **No source URL, no publication date, no confidence level** anywhere.
- Root cause: the script sends only headlines to Gemini, never the links or dates,
  so it *cannot* cite a source. The model also cited "Signal 13", a number that has no
  meaning outside that one prompt.

## 2. What the new `content_engine` does

1. **Research.** Fetches the RSS feeds and keeps only entries that have a link, a
   publication date, and an age of 48h or less. Duplicates are removed and each
   entry gets a stable ID.
2. **Generation.** Gemini sees titles and summaries only, never URLs, and must choose
   **one** story by ID. The URL, date and publisher in the output come from the feed,
   so they cannot be invented.
3. **Validation.** Machine checks for every AGENTS.md rule: 6 slides of at most 30
   words, the slide 6 call to action, exactly 20 unique hashtags, 6 image prompts, why
   it matters, a confidence level, and no unverified links. If a check fails, the
   errors go back to the model once to fix.
4. **Sensitive-claim flags for human review.** Money amounts, percentages, CVEs,
   fines and lawsuits, attribution, "guaranteed compliance"-type promises,
   breach claims, every claim the model lists as used, low confidence, and stories
   older than 24h.
5. **Approval gate.** A package starts as `pending_review`. Approval records who
   approved it and the SHA-256 of the content. **Any edit after approval voids it.**
   Dry-run packages can never be approved.
6. **Output.** `output/packages/<date>/package.json` (for machines and n8n) plus
   `review.md` (for you).

### Commands

```bash
python -m content_engine generate --dry-run    # offline, fixture data
python -m content_engine generate              # live; needs GEMINI_API_KEY
python -m content_engine approve output/packages/2026-11-17/package.json --by "Your Name" --ack-flags
python -m content_engine rehash  output/packages/2026-11-17/package.json   # after hand-editing copy
python -m content_engine check   output/packages/2026-11-17/package.json   # exit 0 = safe to publish
python -m pytest -q
```

GitHub Actions (all manual, none publish):

- **Tests**: runs on every push and needs no secrets.
- **Generate Content Package (review required)**: the live run. It commits the package.
- **Approve Content Package**: only repo writers can run it. It records your GitHub
  username, and you must tick the box confirming you checked the flags.

## 3. Contract for the existing n8n / Facebook flow (no replacement)

n8n keeps doing what it does. It reads `output/packages/<date>/package.json` and publishes **only if all** of these hold:

```
run_mode == "live"
status == "approved"
approval.content_sha256 == content_sha256
validation.errors is empty
```

Text to post: `posts.facebook` (already includes the verified source line). After a successful post, n8n should record the returned post ID (a later milestone will write it back as `published.facebook`).

## 4. Migration cost comparison: keep n8n vs. move publishing into this repo

Prices are approximate and need checking before you decide.

| | Keep n8n for publishing (recommended now) | Replace with GitHub Actions + direct Meta Graph API |
|---|---|---|
| Build effort | Small: add a read-package + gate check step to the existing flow. | Medium: rewrite publishing, token handling, retries and error alerts that n8n already gives you. |
| Running cost | Self-hosted n8n: server cost only (often ~$5/mo VPS or $0 on a machine you already run). n8n Cloud: paid monthly plan. | $0 extra (Actions is free for public repos; 2,000 min/mo on private). |
| Risk | Low: keeps whatever already works. | Rebuilding a working path; Facebook tokens move into GitHub Secrets. |
| Visibility | n8n UI shows each execution. | Logs in Actions; no visual editor. |
| SaaS path | n8n licensing limits embedding it in a commercial SaaS; check the Sustainable Use License before you productise. | Cleaner for SaaS later. |

**Recommendation:** keep n8n for the pilot. Revisit only if (a) n8n Cloud fees exceed
about $20/mo with no self-host option, or (b) you start building the SaaS. The package
contract above means a later migration only swaps the publisher, not the research and
validation.

## 5. What needs your account access (done in your own UI, never pasted into chat)

| Need | Where | Why |
|---|---|---|
| `GEMINI_API_KEY` repo secret | GitHub → Settings → Secrets → Actions | Already referenced by the old workflow; confirm it still works. |
| Run **Generate Content Package** once | GitHub → Actions | First live test of the new engine. |
| Facebook Page token and permissions | Meta for Developers / n8n credentials | Lives in n8n; needs `pages_manage_posts` for the Page. |
| LinkedIn **company page** posting | LinkedIn developer portal | Needs Community Management API approval, which can take weeks. Personal-profile posting is easier. |
| Instagram publishing | Meta Business account linked to the FB Page | Needs a Business/Creator account **and a public image URL**, which requires rendered images first. |
| Decide repo visibility | GitHub | The repo is public, so unreviewed drafts are publicly visible once committed. A private repo is still free within 2,000 Action-minutes/month. |
| Gemini free tier vs paid | Google AI Studio | On the free tier, Google may use prompts to improve its products. Fine for public news; avoid sending client data. |

## 6. Milestones (cheapest first)

1. **Done in this branch:** source-locked package, validation, approval gate, tests and dry run.
2. **Next (you, about 15 min):** add the repo secret if missing, run *Generate Content
   Package*, and read `review.md`. Report errors back so the prompt can be tuned.
3. **Wire n8n to the contract in section 3** and do one Facebook post to a
   **test/unpublished audience** before going live.
4. **Carousel PNG rendering** from slide text with an HTML template and Playwright
   ($0, brand-consistent, no AI image cost). This unblocks Instagram.
5. **Reporting:** weekly pull of Facebook/LinkedIn post insights into a CSV/markdown report.
6. **Scheduling:** add a cron to the generate workflow once 5–10 manual runs pass review.
