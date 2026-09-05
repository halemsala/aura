-- AURA Quant-X administrator schema v1
-- Production DB: engine/aura_quant_x.db. AuditLedger.initialize() applies this shape.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS aura_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    task_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    prev_hash TEXT,
    transaction_hash TEXT,
    hash_algorithm TEXT NOT NULL DEFAULT 'sha256'
);

CREATE INDEX IF NOT EXISTS idx_aura_audit_trace ON aura_audit_events(trace_id, id);
CREATE INDEX IF NOT EXISTS idx_aura_audit_task ON aura_audit_events(task_id, id);

CREATE TRIGGER IF NOT EXISTS trg_aura_audit_no_update
BEFORE UPDATE ON aura_audit_events
BEGIN SELECT RAISE(ABORT, 'aura audit events are append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_aura_audit_no_delete
BEFORE DELETE ON aura_audit_events
BEGIN SELECT RAISE(ABORT, 'aura audit events are append-only'); END;

CREATE TABLE IF NOT EXISTS aura_episodic_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    episode_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    source_event_id INTEGER,
    metadata_json TEXT NOT NULL,
    memory_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    content_hash TEXT,
    embedding_model TEXT,
    embedding_dim INTEGER,
    embedding_json TEXT,
    FOREIGN KEY(source_event_id) REFERENCES aura_audit_events(id)
);

CREATE INDEX IF NOT EXISTS idx_aura_episode_task ON aura_episodic_memory(task_id, id);
CREATE INDEX IF NOT EXISTS idx_aura_episode_type ON aura_episodic_memory(episode_type, id);
CREATE INDEX IF NOT EXISTS idx_aura_episode_embedding ON aura_episodic_memory(embedding_model, embedding_dim, id);

CREATE TABLE IF NOT EXISTS aura_performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    task_id TEXT,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_aura_perf_trace ON aura_performance_metrics(trace_id, id);
CREATE INDEX IF NOT EXISTS idx_aura_perf_stage ON aura_performance_metrics(stage, id);

CREATE TABLE IF NOT EXISTS aura_admin_schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO aura_admin_schema_meta(key, value, updated_at)
VALUES ('schema_version', '1', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
