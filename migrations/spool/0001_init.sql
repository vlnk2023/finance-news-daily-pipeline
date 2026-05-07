CREATE TABLE ingest_spool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT NOT NULL,
    source_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acked_at TEXT,
    CHECK (guid <> ''),
    CHECK (source_id <> ''),
    CHECK (message_id <> '')
);

CREATE INDEX idx_ingest_spool_status_id
ON ingest_spool(status, id);

CREATE INDEX idx_ingest_spool_updated_at
ON ingest_spool(updated_at);

CREATE UNIQUE INDEX idx_ingest_spool_guid_open
ON ingest_spool(guid)
WHERE status IN ('pending', 'retrying');

