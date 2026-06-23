# Profile Foundation

Profiles live in `profiles/*.json`. Each profile controls the public dashboard identity, portal card, render output prefix, and data locations.

## Current Profile

- `profiles/serenity.json`
- Portal URL: `/serenity/`
- Dashboard render command: `.venv/bin/python scripts/serenity_render.py --profile serenity`
- Full site build command: `.venv/bin/python scripts/build_site.py`

## Required Fields

- `slug`: URL folder under the portal, for example `serenity`
- `display_name`: public profile name
- `handle`: X handle without `@`
- `x_url`: profile URL
- `avatar`: path copied from the shared `assets/` folder
- `dashboard.output_prefix`: generated HTML filename prefix
- `dashboard.data_dir`: profile database folder
- `dashboard.reports_dir`: profile investment memo folder

## Before Adding Profile #2

Use Serenity as the boilerplate, but give the new profile separate data paths before generating reports:

- `data/<slug>/db`
- `data/<slug>/reports`
- `data/<slug>/report_queue.json`
- `data/<slug>/report_decisions.json`
- `data/<slug>/report_generation_failures.json`
- `data/<slug>/reason_translations.json`

The portal and renderer are profile-aware now. The remaining work before a second profile is making ingestion, report generation, and scheduled workflows consistently accept a `--profile` argument.
