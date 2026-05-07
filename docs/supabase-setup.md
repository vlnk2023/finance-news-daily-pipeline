# Supabase Setup

Project URL:

```text
https://ujhbempmdbilzajdrhsz.supabase.co
```

## 1. Create Tables

Open Supabase Dashboard, then go to:

```text
SQL Editor -> New query
```

Paste and run:

```text
migrations/supabase/0001_pipeline_schema.sql
```

The schema creates:

- `sources`
- `news_items`
- `translations`
- `daily_digests`
- `pipeline_runs`

`sources`, `news_items`, and `daily_digests` are readable through RLS policies.
Writes should use the service role key from server-side jobs only.

## 2. Configure Secrets

Set these environment variables in GitHub Actions, Hugging Face Space, or a
local `.env` loader:

```text
SUPABASE_URL=https://ujhbempmdbilzajdrhsz.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your service role key>
```

Do not put `SUPABASE_SERVICE_ROLE_KEY` in browser-side code.

## 3. Run Collector Write

```bash
python scripts/run_collector.py --feed-id tg_finance_news_daily --write-supabase
```

For debugging without writing:

```bash
python scripts/run_collector.py --feed-id tg_finance_news_daily --results-json
```

## 4. GitHub Actions

After mirroring this project to GitHub, add repository secrets:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

The workflow template lives at:

```text
.github/workflows/daily-collect.yml
```
