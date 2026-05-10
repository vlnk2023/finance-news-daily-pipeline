# Web Deploy

The `web/` directory is a static frontend for `daily_digests`.

## Configure

Create `web/config.js` from `web/config.example.js`:

```js
window.FINANCE_DIGEST_CONFIG = {
  supabaseUrl: "https://ujhbempmdbilzajdrhsz.supabase.co",
  supabaseAnonKey: "your publishable or legacy anon key",
  strictPublicViews: false,
};
```

Use a publishable or anon key only. Never use `sb_secret_...` in this file.

`strictPublicViews` behavior:

- `false`: frontend first reads `public_*` views, then falls back to base tables.
- `true`: frontend reads `public_*` views only.

Recommended rollout:

1. Apply Supabase migrations `0004_public_read_views.sql` then
   `0005_restrict_public_table_reads.sql`.
2. Verify the frontend works with `strictPublicViews: false`.
3. Switch to `strictPublicViews: true` after migration `0005` is active.

## Local Preview

From the repository root:

```bash
python -m http.server 8787 --directory web
```

Open:

```text
http://127.0.0.1:8787
```

## Deploy

GitHub Pages:

1. Add repository secret:

```text
SUPABASE_PUBLISHABLE_KEY
SUPABASE_STRICT_PUBLIC_VIEWS   (optional, true/false)
```

Use the Supabase publishable key or legacy anon key. Do not use
`sb_secret_...`.

2. In GitHub, open:

```text
Settings -> Pages -> Build and deployment -> Source
```

Select:

```text
GitHub Actions
```

3. Run:

```text
Actions -> Deploy Digest Web -> Run workflow
```

Optional security verification after migrations:

```bash
python scripts/check_public_read_surface.py --base-table-mode restricted
```

Expected after `0005_restrict_public_table_reads.sql`:

- `public_daily_digests` and `public_pipeline_runs`: readable
- `daily_digests` and `pipeline_runs`: restricted

For mixed rollout windows, use:

```bash
python scripts/check_public_read_surface.py --base-table-mode dontcare
```

When running in environments that may not have `SUPABASE_PUBLISHABLE_KEY`:

```bash
python scripts/check_public_read_surface.py --skip-if-missing --base-table-mode dontcare
```

Vercel:

- Framework Preset: `Other`
- Root Directory: `web`
- Build Command: leave empty
- Output Directory: `.`

Cloudflare Pages:

- Build command: leave empty
- Build output directory: `web`
