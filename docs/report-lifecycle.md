# Report Lifecycle

This document defines when Conviction should generate, update, or regenerate a ticker thesis report based on Serenity's public posts.

The goal is to keep each ticker page useful for a reader who wants to quickly understand Serenity's current thesis without rereading every historical post.

## Report States

Each ticker should be treated as one of four states:

1. No report
2. Candidate
3. Full thesis report
4. Full thesis report with dated updates

## No Report

A ticker should not receive a full report when Serenity only mentions it casually.

Examples:

- One-off mention
- List mention
- Meme, joke, or casual reply
- Background comparison
- Sector basket with no specific view
- No clear stance or thesis

These posts should still appear in the dashboard and ticker page, but they should not trigger long-form analysis.

## Candidate

A ticker becomes a report candidate when it has enough signal to deserve human or AI review.

Candidate signals:

- At least 3 to 5 substantive posts
- Repeated mentions across multiple days
- Clear bullish, bearish, or cautious stance
- Serenity states ownership
- Serenity calls it a favorite, high-conviction, or core idea
- Serenity explains why the company matters in a theme
- The ticker appears repeatedly inside a major theme, such as AI photonics, CPO, ASICs, memory, data centers, robotics, defense, or critical materials

Candidate status does not automatically mean a report should be written. It means the ticker is worth reviewing.

## Full Thesis Report

Generate a full thesis report when the ticker has enough material to explain a durable investment thesis.

A full report should answer:

- What is the company?
- Why does Serenity care?
- What was her initial thesis?
- How has the thesis evolved?
- What are the key catalysts?
- What are the key risks?
- What evidence from her posts supports the thesis?
- Does the idea still look attractive today, based only on available posts?

Good report candidates include tickers like AAOI, SIVE, AXTI, NBIS, TSEM, LITE, COHR, and other recurring high-signal names.

The report should cite Serenity's posts inline, preferably with embedded tweet-style cards when available.

## Report Queue

Use `scripts/build_report_queue.py` to decide which tickers deserve reports next.

The queue scans every ticker in `data/db/stocks`, scores the post history, and writes `data/report_queue.json`.

Queue states:

- `needs_report`: enough evidence for a flagship report
- `candidate`: promising, but lower confidence or thinner evidence
- `has_report`: already covered and currently clean
- `needs_update`: existing report has a new update candidate
- `needs_regeneration`: existing report may need a full rewrite

Priority rules:

- Work from `needs_regeneration` and `needs_update` first, because existing report readers may be seeing stale context.
- Then write `needs_report` tickers in descending `report_score`.
- Treat all new reports as flagship reports by default.
- Generate in small batches of 3 to 5, inspect locally, then continue.

Command:

```bash
python scripts/build_report_queue.py
```

## Report Decisions

Use `scripts/build_report_decisions.py` after the update checker and queue builder.

This creates `data/report_decisions.json`, the unified decision layer for automation and public dashboard signals.

Decision actions:

- `write_new_thesis`: uncovered ticker has enough evidence for a flagship investment thesis
- `write_update`: existing thesis has new material context worth adding above the full memo
- `regenerate_thesis`: existing thesis may be structurally stale and should be rewritten
- `watch_for_more_signal`: promising, but not strong enough yet
- `no_action`: published thesis is currently clean

Command:

```bash
python scripts/check_report_updates.py
python scripts/build_report_queue.py
python scripts/build_report_decisions.py
```

To inspect the next automation-ready items:

```bash
jq '.automation_next[:10] | map({ticker, action, priority, report_score, why})' data/report_decisions.json
```

This layer should stay deterministic and cheap. It decides what should happen next; AI generation should remain in the controlled report-generation scripts.

To view only the next report backlog:

```bash
jq '.next_reports[:20] | map({ticker, priority, report_score, why})' data/report_queue.json
```

To preview the next automation-ready investment memo without spending API credits:

```bash
python scripts/generate_report_batch.py --dry-run --limit 5
```

To generate the next memo from the unified decision layer:

```bash
python scripts/generate_report_batch.py --limit 1
```

`generate_report_batch.py` reads `data/report_decisions.json` by default. It processes `write_new_thesis` actions only, uses the guarded single-report generator, translates any new reason snippets, then refreshes report update candidates, queue, decisions, validation, audits, and dashboard rendering.

Existing-report updates are intentionally separate. Hourly sync runs:

```bash
python scripts/check_report_updates.py
python scripts/apply_report_updates.py
python scripts/build_report_queue.py
python scripts/build_report_decisions.py
```

This keeps small “new post changed context” updates cheap and deterministic, while full flagship memo generation remains controlled by the daily/manual batch job.

The guarded memo pipeline:

- selects the next ticker from the full decision list
- generates the report
- translates any new compact reason-panel snippets into `data/reason_translations.json`
- refreshes report update candidates, queue, and decisions
- validates reports
- renders the dashboard
- audits reports and reason-panel translations

The `daily-report` GitHub workflow can run this manually. Its schedule is guarded by the repo variable `AUTO_DAILY_REPORTS=true`, so scheduled generation stays off until explicitly enabled.

The older cluster preview command still exists for exploratory work:

```bash
python scripts/generate_daily_report.py --cluster photonics
```

Long-term automation target:

1. Hourly sync refreshes posts, update candidates, and the report queue.
2. A separate controlled report-generation job processes the next 1 to 3 `needs_report` items.
3. Generated reports render locally or in CI.
4. Quality gates check valid JSON, citation availability, coverage date, and page render.
5. Only reports passing gates are committed.

Do not run unlimited report generation in one job. Reports are expensive, large tickers can time out, and weak outputs pollute the dashboard. Use small batches until the generator has stronger automated quality checks.

## Report Quality Gate

Run `scripts/validate_reports.py` before trusting newly generated reports.

The validator checks:

- report JSON can be parsed
- required fields exist
- `coverage_through` is valid and not beyond local data
- section count is within the flagship range
- enough source posts and section citations exist
- every cited tweet ID exists in `data/db/stocks/{TICKER}.json`
- latest bearish / mixed explicit stance is not silently omitted
- user-facing text does not contain draft / v1 wording

Command:

```bash
python scripts/validate_reports.py
```

The batch generator validates each generated report by default:

```bash
python scripts/generate_report_batch.py --limit 1
```

Use `--no-validate` only for temporary scratch output.

## Browser Render Smoke Test

Run `scripts/smoke_report_render.py` after rendering the dashboard to verify report pages in a real browser.

It checks:

- each report ticker route opens
- report title is visible
- first and last report sections are visible
- at least 8 report headings render
- glossary tooltip markup does not leak into headings
- browser console/page errors are absent

Local setup:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
python scripts/serenity_render.py
.venv/bin/python scripts/smoke_report_render.py
```

The manual GitHub `smoke-test` workflow installs Playwright and runs this browser gate. The hourly sync does not run it because downloading a browser on every hourly data refresh would be slow and unnecessarily fragile.

## Thesis Updates

Add a dated update when a new post changes what a reader needs to know before reading the existing report.

Update-worthy signals:

- Serenity changes stance
- Serenity increases conviction
- Serenity lowers conviction
- Serenity flags a new risk
- Serenity adds a new catalyst
- Serenity corrects or clarifies the original thesis
- Serenity introduces a new framing for the ticker
- A new post materially validates or weakens the existing thesis
- The ticker becomes part of a broader theme that changes the story

Updates should appear above the full report and stay compact.

Recommended update format:

- Date
- Importance level
- Stance direction
- Short title
- 1 paragraph summary
- 3 to 5 bullets
- Source post citations or embedded tweet cards

Rule of thumb:

- Small clarification: no update
- Meaningful new context: add update
- New chapter in the thesis: add update
- New thesis: regenerate the full report

## Regeneration

Regenerate the full report only when the old report becomes structurally misleading or too patched together.

Regeneration-worthy signals:

- Serenity's thesis fundamentally changes
- A ticker goes from minor idea to major recurring idea
- Many updates accumulate and the page feels fragmented
- New posts reveal that the original report missed the core thesis
- The original report is materially stale
- A better narrative can now be written from the full post history

Regeneration should preserve useful source citations from the previous report but rewrite the thesis as one coherent current narrative.

## No-Op Cases

Do not update or regenerate for:

- Repeated wording of the same thesis
- Another list mention
- Price-only victory lap with no new reasoning
- A broad sector mention without ticker-specific insight
- A casual reply that adds no new thesis information
- A post where the ticker is only used as a comparison

## Suggested AI Classification

When new posts arrive, classify each ticker mention before generating content.

Possible labels:

- `background`
- `thesis_relevant`
- `update_worthy`
- `regeneration_worthy`

Suggested fields:

- `ticker`
- `classification`
- `reason`
- `stance`
- `importance`
- `new_information`
- `source_tweet_ids`

Only `update_worthy` and `regeneration_worthy` should produce report changes automatically.

`regeneration_worthy` should ideally be reviewed before replacing the full report.

## Automated Update Check

The hourly sync should run `scripts/check_report_updates.py` after rebuilding the stock database.

The checker uses each report's `coverage_through` date as the boundary. Posts on or before that date are treated as already reviewed. Posts after that date are classified into:

- `ignore`: low-signal mention, list mention, repeated context, or no meaningful thesis change
- `update_candidate`: new post likely deserves a compact dated update above the report
- `regeneration_candidate`: new posts may make the existing report structurally stale

The checker writes `data/report_update_candidates.json`. This file is the automation handoff: it tells us which reports need attention.

`scripts/apply_report_updates.py` runs after the checker. It publishes compact dated updates only when the candidate contains clear thesis signal, such as explicit bullish / bearish stance, high-conviction validation, or a risk post. Low-signal background mentions are not published; their dates are still marked reviewed by advancing `coverage_through`, so the same weak mention does not keep resurfacing.

Current rule:

- Detection is automatic on every sync.
- Compact report updates are auto-published when signal is clear enough.
- Low-signal mentions are auto-ignored and marked reviewed.
- Regeneration candidates should stay review-gated before replacing a flagship report.

Every new or regenerated report should include:

```json
"coverage_through": "YYYY-MM-DD"
```

Set it to the latest Serenity post date that was considered while writing the report, even if the report only cites older foundational posts.

## First Manual Workflow

Before full automation, use a manual review workflow:

```bash
python scripts/generate_next_report.py --dry-run
python scripts/generate_next_report.py
```

`generate_next_report.py` selects the top eligible `needs_report` ticker from `data/report_queue.json`, writes the model output to a temporary draft, validates it, and only then publishes it into `data/reports`. If generation or validation fails, it records the error in `data/report_generation_failures.json` instead of publishing a broken report.

1. Pick one ticker with enough post history.
2. Export or inspect all Serenity posts mentioning that ticker.
3. Decide whether it is a candidate, update, or regeneration case.
4. Generate one full Traditional Chinese report.
5. Compare it against the AAOI report quality bar.
6. Add the report JSON under `data/reports/{TICKER}.json`.
7. Rebuild the dashboard.
8. Review the ticker page locally before pushing.

This keeps quality high while the report format is still evolving.

## Generation Workflow

Use the report generator in two levels:

1. Fast v1 generation
2. Manual or high-quality rewrite

Fast v1 generation should be the default for new tickers. It uses a smaller curated evidence set and produces a concise valid JSON report that can render immediately.

Command:

```bash
python scripts/generate_ticker_report.py SIVE
```

For important tickers, treat the fast report as a draft. Review the rendered page, compare it against the AAOI quality bar, then manually expand or regenerate with a larger evidence set only if needed.

Avoid relying on one giant model call for a final report. Large single-call reports are slower, more likely to time out, and more likely to produce invalid JSON. The preferred approach is:

- generate a reliable v1
- render and inspect locally
- polish the report manually or through smaller targeted passes
- only then push
