---
title: Finance News Daily Collector
emoji: 📰
colorFrom: gray
colorTo: pink
sdk: gradio
app_file: app.py
pinned: false
short_description: Telegram finance news collector
---

# Finance News Daily Collector

Small Gradio app for collecting and previewing posts from the public Telegram
static channel page:

```text
https://t.me/s/FinanceNewsDaily
```

The underlying collector code is also runnable from the command line:

```bash
python scripts/run_collector.py --feed-id tg_finance_news_daily --json
```

To write collected items into Supabase, run the schema in
`migrations/supabase/0001_pipeline_schema.sql`, set `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY`, then run:

```bash
python scripts/run_collector.py --feed-id tg_finance_news_daily --write-supabase
```

Then process the first translation state pass:

```bash
python scripts/translate.py
```

Verify the end-to-end chain for a digest date:

```bash
python scripts/assert_chain_integrity.py --date 2026-05-08 --require-validation-mode any
```

Non-Chinese items are translated with Cloudflare Workers AI
`@cf/meta/m2m100-1.2b` when `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_API_TOKEN` are configured.

Generate a rule-based daily digest:

```bash
python scripts/generate_digest.py
```

The static frontend lives in `web/`. See `docs/web-deploy.md`.
