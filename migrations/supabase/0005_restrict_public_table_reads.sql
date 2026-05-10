do $$
begin
    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'sources'
          and policyname = 'public read sources'
    ) then
        drop policy "public read sources" on public.sources;
    end if;

    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'news_items'
          and policyname = 'public read news items'
    ) then
        drop policy "public read news items" on public.news_items;
    end if;

    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'daily_digests'
          and policyname = 'public read daily digests'
    ) then
        drop policy "public read daily digests" on public.daily_digests;
    end if;

    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'pipeline_runs'
          and policyname = 'public read pipeline runs'
    ) then
        drop policy "public read pipeline runs" on public.pipeline_runs;
    end if;
end $$;

revoke select on public.sources from anon, authenticated;
revoke select on public.news_items from anon, authenticated;
revoke select on public.daily_digests from anon, authenticated;
revoke select on public.pipeline_runs from anon, authenticated;
