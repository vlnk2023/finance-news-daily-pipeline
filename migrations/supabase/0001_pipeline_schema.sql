create extension if not exists pgcrypto;

create table if not exists public.sources (
    id text primary key,
    name text not null,
    platform text not null,
    url text not null,
    language_hint text,
    enabled boolean not null default true,
    collect_config jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.news_items (
    id uuid primary key default gen_random_uuid(),
    source_id text not null references public.sources(id),
    feed_id text not null,
    guid text not null unique,
    content_hash text not null,
    message_id text,
    title text not null default '',
    summary text not null default '',
    source_lang text,
    title_zh text,
    summary_zh text,
    url text not null default '',
    external_url text not null default '',
    external_urls jsonb not null default '[]'::jsonb,
    preview_title text not null default '',
    published_at timestamptz,
    collected_at timestamptz not null default now(),
    translation_status text not null default 'pending',
    raw_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.translations (
    id uuid primary key default gen_random_uuid(),
    source_hash text not null unique,
    source_lang text not null,
    target_lang text not null default 'zh-Hans',
    source_text text not null,
    translated_text text not null,
    provider text not null,
    model text not null,
    quality_score numeric,
    created_at timestamptz not null default now()
);

create table if not exists public.daily_digests (
    id uuid primary key default gen_random_uuid(),
    digest_date date not null unique,
    title text not null,
    markdown text not null,
    json_summary jsonb not null default '{}'::jsonb,
    model text,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.pipeline_runs (
    id uuid primary key default gen_random_uuid(),
    job_type text not null,
    status text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    stats jsonb not null default '{}'::jsonb,
    error text
);

create index if not exists idx_news_items_published_at on public.news_items(published_at desc);
create index if not exists idx_news_items_source_id on public.news_items(source_id);
create index if not exists idx_news_items_content_hash on public.news_items(content_hash);
create index if not exists idx_news_items_translation_status on public.news_items(translation_status);
create index if not exists idx_daily_digests_date on public.daily_digests(digest_date desc);

alter table public.sources enable row level security;
alter table public.news_items enable row level security;
alter table public.translations enable row level security;
alter table public.daily_digests enable row level security;
alter table public.pipeline_runs enable row level security;

create policy "public read sources"
    on public.sources for select
    using (true);

create policy "public read news items"
    on public.news_items for select
    using (true);

create policy "public read daily digests"
    on public.daily_digests for select
    using (true);
