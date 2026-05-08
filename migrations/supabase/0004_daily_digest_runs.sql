create table if not exists public.daily_digest_runs (
    id uuid primary key default gen_random_uuid(),
    digest_date date not null,
    title text not null,
    markdown text not null,
    json_summary jsonb not null default '{}'::jsonb,
    model text,
    generated_at timestamptz not null default now(),
    pipeline_run_id uuid references public.pipeline_runs(id) on delete set null,
    markdown_hash text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_daily_digest_runs_date_time
    on public.daily_digest_runs(digest_date desc, generated_at desc);

create index if not exists idx_daily_digest_runs_hash
    on public.daily_digest_runs(markdown_hash);

alter table public.daily_digest_runs enable row level security;

do $$
begin
    if not exists (
        select 1
        from pg_policies
        where schemaname = 'public'
          and tablename = 'daily_digest_runs'
          and policyname = 'public read daily digest runs'
    ) then
        create policy "public read daily digest runs"
            on public.daily_digest_runs
            for select
            using (true);
    end if;
end $$;
