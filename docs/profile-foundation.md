# Profile Foundation

Profiles live in `profiles/*.json`. Each profile controls the public dashboard identity, portal card, render output prefix, and data locations.

## Current Profiles

- `profiles/serenity.json`
- `profiles/jukan.json`
- Portal URLs: `/serenity/` and `/jukan/`
- Dashboard render commands:
  - `.venv/bin/python scripts/serenity_render.py --profile serenity`
  - `.venv/bin/python scripts/serenity_render.py --profile jukan`
- Full site build command: `.venv/bin/python scripts/build_site.py`

Jukan was initialized from a seven-day calibration window beginning June 16, 2026. Expand the history only after reviewing extraction and ticker normalization quality.

## Required Fields

- `slug`: URL folder under the portal, for example `serenity`
- `display_name`: public profile name
- `handle`: X handle without `@`
- `pronoun_zh`: Traditional Chinese pronoun used in generated memos, for example `她`
- `x_url`: profile URL
- `avatar`: path copied from the shared `assets/` folder
- `dashboard.output_prefix`: generated HTML filename prefix
- `dashboard.data_dir`: profile database folder
- `dashboard.reports_dir`: profile investment memo folder
- `dashboard.raw_tweets`: fetched X posts
- `dashboard.fetch_state`: incremental X cursor/state
- `dashboard.extracted`: per-post AI extraction output
- `dashboard.ticker_map`: ticker metadata and exchange mapping
- `dashboard.prices_cache`: profile price cache

## Before Adding Profile #2

Use Serenity as the boilerplate, but give the new profile separate data paths before generating reports:

- `data/<slug>/db`
- `data/<slug>/reports`
- `data/<slug>/report_queue.json`
- `data/<slug>/report_decisions.json`
- `data/<slug>/report_update_candidates.json`
- `data/<slug>/report_generation_failures.json`
- `data/<slug>/reason_translations.json`

The portal, ingestion, extraction, database build, pricing, renderer, investment memo queue, update detection, report generation, validation, audits, and scheduled workflows are profile-aware.

Before adding profile #2, create its profile JSON and seed a profile-specific `ticker_map.json`. Then run:

```bash
python scripts/fetch_tweets.py --profile <slug>
python scripts/extract.py --profile <slug>
python scripts/build_db.py --profile <slug>
python scripts/verify_data.py --profile <slug>
python scripts/build_site.py
```
