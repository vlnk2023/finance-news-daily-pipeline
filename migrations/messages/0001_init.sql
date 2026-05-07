CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    platform TEXT NOT NULL,
    url TEXT NOT NULL,
    language_hint TEXT,
    tier TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    priority INTEGER NOT NULL DEFAULT 100,
    registry_hash TEXT,
    registry_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_id <> ''),
    CHECK (feed_id <> ''),
    CHECK (source_name <> ''),
    CHECK (platform <> ''),
    CHECK (url <> '')
);

CREATE TABLE source_collect_config (
    source_id TEXT PRIMARY KEY REFERENCES sources(source_id),
    scheduled_times_json TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    lookback_hours INTEGER NOT NULL DEFAULT 12,
    max_items_per_run INTEGER NOT NULL DEFAULT 20,
    timeout_ms INTEGER NOT NULL DEFAULT 12000,
    retries INTEGER NOT NULL DEFAULT 1,
    interval_minutes INTEGER,
    due_window_minutes INTEGER NOT NULL DEFAULT 2,
    min_interval_seconds REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feed_state (
    source_id TEXT PRIMARY KEY REFERENCES sources(source_id),
    last_run_at TEXT,
    last_success_at TEXT,
    last_error_at TEXT,
    next_run_at TEXT,
    consecutive_errors INTEGER NOT NULL DEFAULT 0,
    lease_until TEXT,
    lease_owner TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feed_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    trigger_reason TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    parsed_count INTEGER NOT NULL DEFAULT 0,
    valid_count INTEGER NOT NULL DEFAULT 0,
    window_count INTEGER NOT NULL DEFAULT 0,
    invalid_count INTEGER NOT NULL DEFAULT 0,
    spooled_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    html_length INTEGER,
    html_sha256 TEXT,
    message_block_count INTEGER,
    telegram_widget_found INTEGER,
    html_title TEXT,
    error_message TEXT
);

CREATE TABLE scheduler_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE telegram_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL DEFAULT 'telegram',
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    feed_id TEXT,
    message_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    raw_text_full TEXT NOT NULL,
    search_text TEXT NOT NULL,
    pub_at TEXT,
    pub_str TEXT,
    external_url TEXT,
    external_urls_json TEXT NOT NULL DEFAULT '[]',
    preview_title TEXT,
    media_json TEXT,
    collected_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fts_indexed INTEGER NOT NULL DEFAULT 0,
    fts_indexed_at TEXT,
    fts_error_count INTEGER NOT NULL DEFAULT 0,
    fts_last_error TEXT,
    entities_extracted INTEGER NOT NULL DEFAULT 0,
    entities_extracted_at TEXT,
    entity_error_count INTEGER NOT NULL DEFAULT 0,
    entity_last_error TEXT,
    entity_dictionary_version TEXT,
    entity_needs_rebuild INTEGER NOT NULL DEFAULT 0,
    UNIQUE (platform, source_id, message_id),
    CHECK (guid <> ''),
    CHECK (platform <> ''),
    CHECK (source_id <> ''),
    CHECK (message_id <> ''),
    CHECK (url <> '')
);

CREATE INDEX idx_messages_pub_at_id
ON telegram_messages(pub_at DESC, id DESC);

CREATE INDEX idx_messages_source_pub_at_id
ON telegram_messages(source_id, pub_at DESC, id DESC);

CREATE INDEX idx_messages_fts_pending
ON telegram_messages(fts_indexed, fts_error_count, collected_at);

CREATE INDEX idx_messages_entities_pending
ON telegram_messages(entities_extracted, entity_error_count, collected_at);

CREATE VIRTUAL TABLE telegram_messages_fts USING fts5(
    title,
    summary,
    raw_text_full,
    source_name,
    tokenize='unicode61',
    content='telegram_messages',
    content_rowid='id'
);

CREATE TABLE dead_letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT,
    source_id TEXT,
    message_id TEXT,
    stage TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dead_letters_status_retry
ON dead_letters(status, next_retry_at, id);

CREATE TABLE search_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    mode TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_search_events_created_at
ON search_events(created_at);

CREATE TABLE entity_dictionary_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dictionary_version TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE entity_dictionary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    relations_json TEXT,
    match_mode TEXT NOT NULL DEFAULT 'contains',
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_type, normalized_name)
);

CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    aliases_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_type, normalized_name)
);

CREATE TABLE entity_alias_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    base_confidence REAL NOT NULL DEFAULT 1.0,
    priority INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(normalized_alias, entity_id)
);

CREATE TABLE message_entity_candidates (
    message_id INTEGER NOT NULL REFERENCES telegram_messages(id),
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    alias TEXT NOT NULL,
    confidence REAL NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    disambiguation_status TEXT NOT NULL DEFAULT 'candidate',
    evidence_json TEXT,
    extractor TEXT NOT NULL,
    extracted_with_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(message_id, entity_id, alias)
);

CREATE TABLE message_entities (
    message_id INTEGER NOT NULL REFERENCES telegram_messages(id),
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL DEFAULT 'MENTIONS',
    confidence REAL NOT NULL DEFAULT 1.0,
    extractor TEXT NOT NULL DEFAULT 'dictionary',
    extracted_with_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(message_id, entity_id, relation_type)
);

CREATE TABLE entity_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id INTEGER NOT NULL REFERENCES entities(id),
    target_entity_id INTEGER NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL,
    evidence_message_id INTEGER REFERENCES telegram_messages(id),
    extractor TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_entity_id, target_entity_id, relation_type, evidence_message_id)
);

