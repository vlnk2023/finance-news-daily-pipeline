# Web Deploy

The `web/` directory is a static frontend for `daily_digests`.

## Configure

Create `web/config.js` from `web/config.example.js`:

```js
window.FINANCE_DIGEST_CONFIG = {
  supabaseUrl: "https://ujhbempmdbilzajdrhsz.supabase.co",
  supabaseAnonKey: "your publishable or legacy anon key",
};
```

Use a publishable or anon key only. Never use `sb_secret_...` in this file.

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

Vercel:

- Framework Preset: `Other`
- Root Directory: `web`
- Build Command: leave empty
- Output Directory: `.`

Cloudflare Pages:

- Build command: leave empty
- Build output directory: `web`
