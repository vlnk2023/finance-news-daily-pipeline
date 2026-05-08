do $$
begin
    if not exists (
        select 1
        from pg_policies
        where schemaname = 'public'
          and tablename = 'pipeline_runs'
          and policyname = 'public read pipeline runs'
    ) then
        create policy "public read pipeline runs"
            on public.pipeline_runs
            for select
            using (true);
    end if;
end $$;
