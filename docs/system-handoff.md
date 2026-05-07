# Finance News Daily Pipeline Handoff

Last updated: 2026-05-07

## Current State

The system is now a working free-tier news pipeline:

```text
Telegram public channels
  -> GitHub Actions scheduled collector
  -> Supabase Postgres storage
  -> Cloudflare Workers AI translation
  -> rule-based Chinese daily digest
  -> GitHub Pages static frontend
  -> Hugging Face Space manual console
```

Completed:

- Hugging Face Space deployed at `phily23/trans26`.
- GitHub repository created at `vlnk2023/finance-news-daily-pipeline`.
- Supabase schema created and collector writes to Supabase.
- GitHub Actions workflow runs collection, translation, and digest generation.
- Cloudflare Workers AI provider added for non-Chinese translation through `@cf/meta/m2m100-1.2b`.
- Static frontend deployed through GitHub Pages.
- 10 Telegram feeds are configured in `src/config/feed-registry.json`.

Current important commits:

- `03c7930` Add Supabase pipeline storage
- `1f8798d` Add Cloudflare translation provider
- `13997bd` Add rule based daily digest
- `dd76a54` Add static digest frontend
- `7ac8a3a` Add requested Telegram feeds

## Remaining Work

Priority next steps:

1. Improve digest quality with an LLM summarizer instead of the current rule-based digest.
2. Add source quality scoring and per-source filtering to reduce noise.
3. Add frontend filters: date, source, keyword, category.
4. Add pipeline run logging into `pipeline_runs`.
5. Add failure notifications through Telegram or Discord.
6. Add retry/quotas around Cloudflare translation.
7. Add a manual backfill script for historical channels.
8. Add a real deployment target for the static frontend if GitHub Pages is not enough, such as Vercel or Cloudflare Pages.

## Repository Layout

```text
collector/
  config/                 Feed registry loader
  fetchers/               Telegram static page fetcher
  parsers/                Telegram HTML parser
  runner.py               Collection orchestration
  storage/supabase_store.py
  translation/            Language detection and Cloudflare provider

scripts/
  run_collector.py        Collect feeds and optionally write Supabase
  translate.py            Translate pending items
  generate_digest.py      Rule-based daily digest

src/config/feed-registry.json
  Telegram source registry

migrations/supabase/
  Supabase SQL schema

web/
  Static frontend for daily_digests

.github/workflows/
  daily-collect.yml       Data pipeline workflow
  deploy-web.yml          GitHub Pages deployment
```

## Platform Responsibilities

### GitHub Actions

Main role:

- Scheduled free batch compute.
- Runs the production data pipeline.

Workflow:

```text
.github/workflows/daily-collect.yml
```

Current steps:

```text
checkout
setup-python
pip install -r requirements.txt
python scripts/run_collector.py --write-supabase
python scripts/translate.py
python scripts/generate_digest.py
```

Required repository secrets:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

Deployment conditions:

- Repository must have Actions enabled.
- Secrets must exist under:

```text
Settings -> Secrets and variables -> Actions -> Repository secrets
```

Improvement space:

- Add `pipeline_runs` writes for each step.
- Split collect, translate, and digest into separate jobs.
- Add retries and timeout controls per feed.
- Add `workflow_dispatch` inputs for feed ID, date, and backfill mode.

### Supabase

Main role:

- Database and persistent system state.

Project URL:

```text
https://ujhbempmdbilzajdrhsz.supabase.co
```

Schema:

```text
migrations/supabase/0001_pipeline_schema.sql
```

Tables:

```text
sources
news_items
translations
daily_digests
pipeline_runs
```

Current table purpose:

- `sources`: configured Telegram sources.
- `news_items`: normalized collected messages.
- `translations`: translation memory cache.
- `daily_digests`: generated Chinese daily digests.
- `pipeline_runs`: reserved for future run logs.

Required keys:

- `SUPABASE_URL`: project URL.
- `SUPABASE_SERVICE_ROLE_KEY`: server-side write key, starts with `sb_secret_...`.
- `SUPABASE_PUBLISHABLE_KEY`: browser-safe publishable or legacy anon key for the static frontend.

How to find keys:

1. Open Supabase dashboard.
2. Select project.
3. Go to:

```text
Project Settings -> API
```

Use:

- `Project URL` for `SUPABASE_URL`.
- `Secret keys -> default` for `SUPABASE_SERVICE_ROLE_KEY`.
- `Publishable key` or legacy `anon` key for `SUPABASE_PUBLISHABLE_KEY`.

Security rule:

- Never put `sb_secret_...` in frontend code.
- `SUPABASE_SERVICE_ROLE_KEY` only belongs in GitHub Secrets, server jobs, or trusted backend environments.

Improvement space:

- Add read-only database views for the frontend.
- Add RLS policies by table/view rather than broad public select.
- Add indexes for search and date/source filtering.
- Add full-text search over translated text.
- Add retention or archive rules if the free database grows too large.

### Cloudflare Workers AI

Main role:

- Translation engine for non-Chinese content.

Current model:

```text
@cf/meta/m2m100-1.2b
```

Code:

```text
collector/translation/cloudflare.py
scripts/translate.py
```

Required GitHub Secrets:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

How to get `CLOUDFLARE_ACCOUNT_ID`:

1. Open Cloudflare dashboard.
2. Select the account.
3. Copy `Account ID` from the account overview.

How to create `CLOUDFLARE_API_TOKEN`:

1. Open:

```text
My Profile -> API Tokens -> Create Token -> Custom token
```

2. Add permission:

```text
Account -> Workers AI -> Edit
```

3. Scope it to the selected account.
4. Copy the generated token once.

Current translation flow:

```text
news_items where translation_status = pending
  -> detect source language
  -> if Chinese: copy title/summary to title_zh/summary_zh
  -> else: check translations cache by hash
  -> if cache miss: call Cloudflare Workers AI
  -> write translations
  -> update news_items
```

Improvement space:

- Add batch translation for lower request overhead.
- Add per-day translation quota.
- Add retry with backoff.
- Add fallback providers: Gemini, Groq, HF Space NLLB, Argos.
- Add quality scoring for translated output.

### Hugging Face Space

Main role:

- Manual collector/debug UI.
- Public demo surface.
- Potential future fallback HTTP API.

Current Space:

```text
https://huggingface.co/spaces/phily23/trans26
```

Runtime:

- Gradio app in `app.py`.
- `README.md` declares `sdk: gradio` and `app_file: app.py`.

Current use:

- Manually collect from configured or custom Telegram `/s/` URL.
- Inspect parsed rows and raw JSON.

Potential future role:

- Add `/health`.
- Add `/translate_batch`.
- Add `/collect_once`.
- Use as a fallback endpoint when GitHub Actions or Cloudflare translation fails.

Improvement space:

- Add Supabase read/write toggle in the UI.
- Add source registry editor.
- Add manual backfill controls.
- Add fallback translation model such as Argos or NLLB if free CPU is enough.

### GitHub Pages

Main role:

- Static frontend hosting.

Workflow:

```text
.github/workflows/deploy-web.yml
```

Frontend:

```text
web/index.html
web/styles.css
web/app.js
web/config.example.js
```

Required GitHub Secret:

```text
SUPABASE_PUBLISHABLE_KEY
```

Pages setup:

```text
Settings -> Pages -> Build and deployment -> Source -> GitHub Actions
```

Expected public URL:

```text
https://vlnk2023.github.io/finance-news-daily-pipeline/
```

Runtime behavior:

- `deploy-web.yml` generates `web/config.js` from GitHub Secrets.
- Browser reads Supabase `daily_digests` through REST API.
- No service role key is exposed.

Improvement space:

- Add digest detail route by date.
- Add source/news list pages.
- Add keyword search and source filter.
- Add category summary charts.
- Add deploy target to Vercel or Cloudflare Pages for custom domain support.

### Telegram

Main role:

- Source data.

The collector uses public static Telegram pages:

```text
https://t.me/s/<channel>
```

Not the normal app/channel page:

```text
https://t.me/<channel>
```

Current configured feeds:

```text
tg_finance_news_daily
tg_discord_bypass
tg_ai_experience_ru
tg_geph_announce
tg_bloomberg
tg_quanxiaowa
tg_geekshare
tg_bloombergs
tg_bloombergu
tg_bloombergq
```

Feed configuration file:

```text
src/config/feed-registry.json
```

Important fields:

- `feed_id`: unique pipeline ID.
- `source_id`: source ID written to Supabase.
- `source_name`: display name.
- `url`: must use `/s/`.
- `language_hint`: expected language.
- `enabled`: whether to collect.
- `collect.lookback_hours`: date filtering.
- `collect.max_items_per_run`: max messages per run.

Improvement space:

- Add source scoring.
- Add source categories.
- Add feed-level translation provider override.
- Add source-specific filters.

## Data Flow

### Production Pipeline

```text
GitHub Actions cron or manual run
  -> scripts/run_collector.py --write-supabase
  -> collector loads src/config/feed-registry.json
  -> TelegramFetcher downloads https://t.me/s/<channel>
  -> TelegramParser normalizes messages
  -> CollectionRunner enriches with feed metadata
  -> SupabaseStore upserts sources and news_items
  -> scripts/translate.py reads pending news_items
  -> detect_language routes items
  -> Chinese items are copied into *_zh fields
  -> non-Chinese items are translated by Cloudflare Workers AI
  -> translations cache is written
  -> news_items are marked translated or failed
  -> scripts/generate_digest.py reads translated items for today
  -> daily_digests is upserted
```

### Frontend Flow

```text
Browser opens GitHub Pages site
  -> web/config.js provides Supabase URL and publishable key
  -> web/app.js calls /rest/v1/daily_digests
  -> latest 30 digests are rendered
```

### Manual Debug Flow

```text
User opens Hugging Face Space
  -> selects feed or custom Telegram URL
  -> Gradio calls CollectionRunner
  -> parsed rows and raw JSON are shown
```

## Environment Variables And Secrets

Server-side secrets:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

Frontend secret-like public config:

```text
SUPABASE_PUBLISHABLE_KEY
```

Local PowerShell test:

```powershell
$env:SUPABASE_URL="https://ujhbempmdbilzajdrhsz.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="sb_secret_..."
python scripts\run_collector.py --write-supabase
python scripts\translate.py
python scripts\generate_digest.py
```

Do not commit:

```text
web/config.js
sb_secret_...
CLOUDFLARE_API_TOKEN
```

## Common Operations

Add a new Telegram source:

1. Test the static URL:

```powershell
python scripts\fetch_finance_news_daily.py --url https://t.me/s/<channel> --limit 3 --json
```

2. Add an entry to:

```text
src/config/feed-registry.json
```

3. Validate:

```powershell
python -c "from collector.config import load_enabled_feeds; print(len(load_enabled_feeds('src/config/feed-registry.json', platform='telegram')))"
python scripts\run_collector.py --feed-id <feed_id> --results-json
```

4. Commit and push:

```powershell
git add src/config/feed-registry.json
git commit -m "Add <source> Telegram feed"
git push github main
git push origin main
```

Run full pipeline manually:

```text
GitHub -> Actions -> Daily Finance Collect -> Run workflow
```

Deploy frontend manually:

```text
GitHub -> Actions -> Deploy Digest Web -> Run workflow
```

Check data:

```text
Supabase -> Table Editor -> news_items
Supabase -> Table Editor -> translations
Supabase -> Table Editor -> daily_digests
```

## Known Limitations

- Digest generation is rule-based, not LLM-quality yet.
- Telegram `/s/` pages expose only static public content and may omit media-rich/private content.
- Cloudflare translation quality varies by language and length.
- Current frontend only displays daily digests, not raw news.
- `pipeline_runs` table exists but is not written yet.
- Local Windows tests using `tempfile` can fail under restricted filesystem permissions; core tests pass when excluding those tempfile-dependent cases.

## Suggested Next Conversation Starting Point

Use this prompt:

```text
Continue from docs/system-handoff.md. The pipeline is live with GitHub Actions, Supabase, Cloudflare Workers AI translation, rule-based daily_digests, and GitHub Pages frontend. Next task: improve <specific area>.
```

Recommended next area:

```text
Replace rule-based digest generation with LLM-assisted Chinese summaries while preserving rule-based output as fallback.
```
