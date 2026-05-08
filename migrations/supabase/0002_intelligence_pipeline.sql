create table if not exists public.intelligence_clusters (
    id uuid primary key default gen_random_uuid(),
    digest_date date not null,
    cluster_key text not null,
    representative_item_guid text not null references public.news_items(guid) on delete cascade,
    canonical_title text not null default '',
    canonical_url text not null default '',
    source_ids jsonb not null default '[]'::jsonb,
    item_count integer not null default 0,
    language_mix jsonb not null default '{}'::jsonb,
    importance_score numeric not null default 0,
    status text not null default 'built',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (digest_date, cluster_key)
);

create table if not exists public.cluster_members (
    id uuid primary key default gen_random_uuid(),
    cluster_id uuid not null references public.intelligence_clusters(id) on delete cascade,
    digest_date date not null,
    news_item_guid text not null references public.news_items(guid) on delete cascade,
    source_id text not null,
    similarity_reason text not null default '',
    created_at timestamptz not null default now(),
    unique (cluster_id, news_item_guid)
);

create table if not exists public.digest_candidates (
    id uuid primary key default gen_random_uuid(),
    digest_date date not null,
    cluster_id uuid not null references public.intelligence_clusters(id) on delete cascade,
    representative_item_guid text not null references public.news_items(guid) on delete cascade,
    rank integer not null,
    importance_score numeric not null default 0,
    source_ids jsonb not null default '[]'::jsonb,
    status text not null default 'selected',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (digest_date, cluster_id)
);

create index if not exists idx_intelligence_clusters_digest_date
    on public.intelligence_clusters(digest_date desc, importance_score desc);
create index if not exists idx_cluster_members_cluster_id
    on public.cluster_members(cluster_id);
create index if not exists idx_digest_candidates_digest_date
    on public.digest_candidates(digest_date desc, rank asc);

alter table public.intelligence_clusters enable row level security;
alter table public.cluster_members enable row level security;
alter table public.digest_candidates enable row level security;

create policy "public read intelligence clusters"
    on public.intelligence_clusters for select
    using (true);

create policy "public read digest candidates"
    on public.digest_candidates for select
    using (true);
