create or replace view public.public_daily_digests as
select
    digest_date,
    title,
    markdown,
    generated_at,
    model,
    json_summary
from public.daily_digests;

create or replace view public.public_pipeline_runs as
select
    job_type,
    status,
    started_at,
    finished_at,
    stats,
    error,
    stats ->> 'digest_date' as digest_date
from public.pipeline_runs;

grant usage on schema public to anon, authenticated;
grant select on public.public_daily_digests to anon, authenticated;
grant select on public.public_pipeline_runs to anon, authenticated;
