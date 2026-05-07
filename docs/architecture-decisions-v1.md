# Architecture Decisions V1

This document freezes the core V1 decisions before implementing SQLite storage.
It is intentionally strict: each item is a constraint that later code should
respect unless a new decision explicitly replaces it.

## Scope

V1 is a single-node Telegram collection and local search system.

Hard boundaries:

- Deployment target: one lightweight VPS, around 2 CPU cores and 1 GB RAM.
- Source type: Telegram public static pages under `https://t.me/s/<channel>`.
- Crawl window: current static page only, with 12-hour lookback.
- Historical completeness: best-effort current-window collection, not a full archive.
- Storage core: SQLite + FTS5.
- Search: keyword search first; semantic search is optional future work.
- Graph: lightweight entity relations in SQLite, not graph inference.
- Auth: no V1 login system; rely on deployment boundary and query guards.

## Source Of Truth

The only business source of truth is the SQLite `telegram_messages` table.

Derived and rebuildable layers:

- `telegram_messages_fts`
- entity extraction tables
- search logs
- optional Redis cache
- optional DuckDB / FAISS indexes

Raw full HTML is not stored by default. Each feed run records HTML diagnostics:

- `html_length`
- `html_sha256`
- `message_block_count`
- `telegram_widget_found`
- `html_title`

Debug HTML may be saved only for parse-empty diagnostics with short retention.

## Identity And Idempotency

Telegram `message_id` is unique only within one source, not globally.

Business identity:

```text
guid = platform + ":" + source_id + ":" + message_id
```

Example:

```text
telegram:tg_finance_news_daily:12345
```

SQLite must enforce:

```sql
UNIQUE (platform, source_id, message_id);
UNIQUE (guid);
CHECK (guid <> '');
CHECK (source_id <> '');
CHECK (message_id <> '');
```

If `message_id` is missing, the item is invalid and must not enter messages,
FTS5, or entity tables. It is counted as invalid and logged.

No hash is used for business identity, so hash collision is not a V1 concern.

## Parsing Policy

Parser output is normalized into a standard item and then validated before
spooling or storage.

Required fields for valid items:

- `source_id`
- `message_id`
- `guid`
- `url`

Telegram edits are ignored in V1. First-seen wins:

```text
existing source_id + message_id -> ignore
```

Telegram deletions are ignored in V1. Already collected messages remain local.

External links:

- `external_url`: first non-Telegram HTTP(S) link for display.
- `external_urls`: all non-Telegram HTTP(S) links, preserving order and de-duped.
- SQLite stores both `external_url` and `external_urls_json`.

Media is not supported in V1. No media download, OCR, thumbnail generation, or
Telegram CDN preservation. Users can open the original Telegram message URL.

## Crawl Window And Scheduling

V1 only crawls the current `/s/` page and keeps items within 12 hours:

```text
pub_at >= now - 12h
```

If the system is down for more than 12 hours, missing messages are not backfilled.

Scheduling is per source, not global. Runtime scheduling reads SQLite tables,
not JSON files.

Supported triggers:

- `scheduled_times_local`
- `interval_minutes`

The daemon checks every minute. Fixed-time and interval triggers may both exist.
If both are due, they are merged into one collection run.

Same-source concurrency is forbidden:

- If a source is already running, a new due event is skipped.
- Skips are recorded as scheduler events.
- Source lease TTL prevents stuck running states.

Global concurrency is a hard upper bound, and source-level rate limits must also
pass:

```text
can_dispatch =
  global_running_count < max_global_concurrency
  AND source not running
  AND source rate limit passed
  AND disk/backpressure healthy
```

Default global concurrency should be 3 to 5.

Fetch failures are not immediately rescheduled. The HTTP layer may do 0-1 short
retry, then the source waits for the next due schedule.

## Runtime Config

`feed-registry.json` is a versioned import source, not runtime truth.

Runtime truth lives in SQLite:

- `sources`
- `source_collect_config`
- `feed_state`
- `feed_runs`

JSON sync rules:

- New JSON source inserts a row into SQLite.
- Existing SQLite runtime status is preserved.
- JSON `enabled` is only an initial default, not an override.
- Runtime status uses expressive values such as `active`, `paused`, `disabled`,
  and `error_hold`.
- Scheduled times, lookback, timeout, retries, and interval are stored in
  `source_collect_config`.

`source_id` received from API clients is never trusted. It must be checked
against the SQLite `sources` table and must be enabled/active before use.

## Process Model

V1 uses two processes:

```text
collector-daemon
api-server
```

`collector-daemon` owns:

- scheduling
- fetch and parse
- durable spool
- single SQLite writer
- FTS5 compensation
- entity extraction compensation
- DLQ retry
- cleanup tasks

`api-server` owns:

- latest message API
- search API
- detail API
- sources API
- health API
- lightweight `search_events`

SQLite must run in WAL mode so the daemon can write while the API reads.

## Durable Ingest

If crash recovery must be lossless after parsing, every valid item is durably
spooled before it is queued for writing:

```text
spool append -> queue put -> messages write -> spool ack
```

The queue is an acceleration layer. Spool is the reliability layer.

Spool and messages use separate SQLite database files:

```text
data/spool.sqlite3
data/messages.sqlite3
```

The queue should carry `spool_id`, not the full item. On recovery, pending spool
rows can be replayed.

Cross-database atomicity is not required. If messages write succeeds but spool
ack fails, replay is safe because messages has unique constraints.

Spool retention:

- acked rows: keep 48 hours, then purge.
- failed/expired rows: keep 7 days.
- pending/retrying rows older than 72 hours become expired.
- spool is not permanent history.

Disk guard:

- `<80%`: normal.
- `80-90%`: warning, slow down.
- `90-95%`: critical, pause fetch, drain and cleanup.
- `>=95%`: emergency, stop non-essential writes.

Never silently delete pending spool rows because of disk pressure.

## SQLite Write Model

SQLite writing is single-writer.

Fetch and parse may run concurrently, but only one writer worker writes
`messages.sqlite3` and FTS5.

SQLite PRAGMAs:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
```

Realtime writes:

- batch items
- write messages first
- best-effort write FTS5 immediately
- mark `fts_indexed = 1` on success
- leave `fts_indexed = 0` on failure

Messages are stronger than FTS5:

```text
telegram_messages = strong source of truth
FTS5 = eventually consistent derived index
entities = eventually consistent derived index
```

Historical/backfill style writes:

- insert messages in bulk
- build FTS5 in batches of around 1000
- track state with `fts_indexed`

FTS5 failures are not DLQ immediately. They are retried by compensation. After
repeated failures, write dead-letter with `stage='fts_index'`.

## FTS5 Search

V1 uses SQLite FTS5 with `unicode61`.

Indexed fields:

- `title`
- `summary`
- `raw_text_full`
- `source_name`

Default ranking:

```sql
bm25(telegram_messages_fts, 5.0, 2.0, 1.0, 0.5)
```

Meaning:

- title: highest weight
- summary: medium weight
- raw text: recall fallback
- source name: low weight

Structured fields such as `source_id`, `pub_at`, `guid`, and URL fields are
filtered with SQL, not FTS.

Chinese search V1 strategy:

- use FTS5 `unicode61`
- add `search_text` for lightweight LIKE fallback
- monitor failed and zero-result searches
- do not introduce jieba or other tokenizers in V1

V2 upgrade path:

- add `tokens_text`
- generate segmented Chinese tokens
- add tokens to FTS5
- deploy without affecting realtime crawling

Search logs:

- store `search_events` in `messages.sqlite3`
- write failures must not affect user searches
- retain 30 days

## API Query Rules

Frontend never reads SQLite directly. All access goes through API.

No V1 login system, but API must still apply safety guards:

- bind to localhost or a controlled reverse proxy
- no arbitrary SQL endpoint
- query length limit
- limit maximum 100
- cursor pagination only
- field trimming in DTOs
- source whitelist validation

API endpoints:

- `GET /api/messages/latest`
- `GET /api/messages/search`
- `GET /api/messages/{guid}`
- `GET /api/sources`
- `GET /api/health`

Pagination:

- latest: cursor based on `pub_at + id`
- search: cursor based on `rank + pub_at + id + query_hash`
- no unbounded offset pagination

Search defaults:

- default search range: recent N days, recommended 30
- normal maximum: 180 days
- all-time search is explicit and configuration-gated
- all-time LIKE fallback is not allowed

Source filters:

- optional single or multiple `source_id`
- all source IDs must be validated against SQLite `sources`
- max source filter count recommended 10
- default all sources still uses default time range

## Dead Letter

Dead Letter is required but lightweight.

Preferred storage is a SQLite table in `messages.sqlite3`; JSONL is only a
fallback if SQLite cannot be written.

Dead-letter stages:

- `validate`
- `write`
- `fts_index`
- `entity_extract`

Fetch/network failures belong mainly in `feed_runs`, not item-level DLQ.

Retention:

- pending retry max around 3 attempts
- resolved/permanently failed/expired cleanup after about 7 days

FTS5 failures normally use `fts_indexed=0` compensation first. DLQ is for
repeated or extreme failures.

## Entities

V1 includes lightweight entities, but not NLP-heavy extraction.

Extraction source:

- dictionary
- regex rules
- ticker-like rules

No LLM inference and no complex NER in V1.

Runtime entity dictionary lives in SQLite. JSON/CSV are import sources only.

Entity extraction is post-write and eventually consistent:

```text
messages inserted -> entities_extracted = 0 -> extraction worker -> entities_extracted = 1
```

Extraction can be rebuilt:

- delete derived message entity rows
- reset extraction flags
- rerun extraction by source/time/all

Ambiguous aliases:

- keep all candidates
- only high-confidence clear winner becomes primary
- ambiguous candidates do not enter official `message_entities`
- preserve evidence for later correction

Semantic relations:

- `message_entities` stores mentions.
- `entity_relations` stores only explicit semantic relations.
- Co-occurrence is not treated as semantic relation.
- Every semantic relation must have `extractor`, `confidence`, and optional
  `evidence_message_id`.

Relation sources:

- dictionary metadata
- explicit regex rules
- manual/external metadata later

No V1 causal or inferred relations from co-occurrence.

Dictionary updates:

- version the dictionary
- new messages use the latest version
- historical messages are not automatically rebuilt
- rebuild is explicit by script with source/time/all scope

## Backup And Recovery

Must back up:

- `messages.sqlite3`
- `spool.sqlite3`
- runtime config tables

Suggested backup:

- entity dictionary
- alias candidates
- feed registry JSON if not already in git

Use SQLite online backup, not raw copy of active WAL databases:

```bash
sqlite3 data/messages.sqlite3 ".backup 'backups/messages-YYYYMMDD-HHMM.sqlite3'"
sqlite3 data/spool.sqlite3 ".backup 'backups/spool-YYYYMMDD-HHMM.sqlite3'"
```

Recommended cadence:

- messages: daily full backup plus 6-hour snapshots
- spool: hourly backup
- config/dictionary: after changes
- remote sync: daily

Retention:

- local hourly: 24
- local daily: 14 days
- weekly: 8 weeks
- remote daily: 30 days

Restore flow:

1. Stop daemon and API.
2. Restore messages DB.
3. Restore spool DB.
4. Start daemon.
5. Replay pending spool.
6. Run FTS5 compensation.
7. Run entity extraction compensation.
8. Start API.

Backups must be restore-tested.

## Migrations And SQL

V1 uses hand-written SQL migrations, not ORM migrations.

Separate migration directories:

```text
migrations/messages/
migrations/spool/
```

Each database has `schema_migrations`.

Migration runner rules:

- sort by filename
- run each unapplied migration in one transaction
- write applied version after success
- stop on first failure
- check FTS5 availability before messages migrations

Code uses Python standard `sqlite3` plus hand-written SQL.

SQL is wrapped in store/repository classes:

- `sqlite_connection.py`
- `message_store.py`
- `spool_store.py`
- `source_store.py`
- `entity_store.py`
- `search_store.py`

Business code must not build SQL by string interpolation. All user input is
parameterized and validated.

## Implementation Order

Implement storage only after this decision document is accepted.

Recommended order:

1. SQL migrations for `messages.sqlite3` and `spool.sqlite3`.
2. SQLite connection helpers and FTS5 availability check.
3. `SpoolStore`.
4. `MessageStore` with idempotent insert and FTS5 compensation state.
5. single writer worker.
6. scheduler reads SQLite `sources` and `source_collect_config`.
7. source sync script from JSON.
8. basic search service and API.
9. entity dictionary and post-write extraction worker.
10. backup, cleanup, and maintenance scripts.

