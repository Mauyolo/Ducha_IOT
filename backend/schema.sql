PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMINISTRADOR','MODERADOR')),
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_login TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS residents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    dni TEXT,
    room TEXT,
    email TEXT,
    preferred_temp REAL NOT NULL DEFAULT 24.0,
    default_goal_l REAL,
    condition_mode TEXT NOT NULL DEFAULT 'INTELIGENTE' CHECK(condition_mode IN ('TRADICIONAL','INTELIGENTE')),
    experiment_sequence TEXT NOT NULL DEFAULT 'T-I',
    enabled INTEGER NOT NULL DEFAULT 1,
    consent_valid INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    room TEXT,
    status TEXT NOT NULL DEFAULT 'DESCONECTADO',
    last_seen TEXT,
    firmware_version TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_programs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    device_id INTEGER REFERENCES devices(id),
    planned_mode TEXT NOT NULL CHECK(planned_mode IN ('TRADICIONAL','INTELIGENTE')),
    scheduled_at TEXT,
    sequence_no INTEGER,
    status TEXT NOT NULL DEFAULT 'PENDIENTE',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    device_id INTEGER REFERENCES devices(id),
    program_id INTEGER REFERENCES session_programs(id),
    mode TEXT NOT NULL CHECK(mode IN ('TRADICIONAL','INTELIGENTE')),
    status TEXT NOT NULL DEFAULT 'PREPARADA',
    started_at TEXT,
    ended_at TEXT,
    total_duration_s INTEGER NOT NULL DEFAULT 0,
    effective_duration_s INTEGER NOT NULL DEFAULT 0,
    pause_count INTEGER NOT NULL DEFAULT 0,
    pause_duration_s INTEGER NOT NULL DEFAULT 0,
    volume_total_l REAL NOT NULL DEFAULT 0,
    avg_flow_lmin REAL,
    max_flow_lmin REAL,
    avg_temp_c REAL,
    max_temp_c REAL,
    target_l REAL,
    quality TEXT NOT NULL DEFAULT 'VALIDA',
    experimental INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    stop_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    flow_lmin REAL NOT NULL,
    volume_l REAL NOT NULL,
    temp_c REAL,
    state TEXT,
    rssi INTEGER,
    source TEXT NOT NULL DEFAULT 'MQTT'
);
CREATE INDEX IF NOT EXISTS idx_measurements_session_ts ON measurements(session_id, ts);

CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    data_json TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    session_id INTEGER REFERENCES sessions(id),
    resident_id INTEGER REFERENCES residents(id),
    device_id INTEGER REFERENCES devices(id),
    kind TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('BAJA','MEDIA','ALTA','CRITICA')),
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK(status IN ('PENDIENTE','REVISADA','RESUELTA')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    handled_by INTEGER REFERENCES users(id),
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);

CREATE TABLE IF NOT EXISTS ai_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    algorithm TEXT NOT NULL,
    version TEXT NOT NULL UNIQUE,
    mae REAL,
    rmse REAL,
    r2 REAL,
    sample_size INTEGER NOT NULL DEFAULT 0,
    trained_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    file_path TEXT
);

CREATE TABLE IF NOT EXISTS ai_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    session_id INTEGER REFERENCES sessions(id),
    model_id INTEGER REFERENCES ai_models(id),
    predicted_l REAL NOT NULL,
    target_l REAL NOT NULL,
    reduction_pct REAL NOT NULL,
    frozen INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS consumption_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    source TEXT NOT NULL,
    predicted_l REAL,
    reduction_pct REAL NOT NULL,
    target_l REAL NOT NULL,
    model_version TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_targets_resident_active ON consumption_targets(resident_id, active);

CREATE TABLE IF NOT EXISTS surveys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    session_id INTEGER REFERENCES sessions(id),
    moment TEXT NOT NULL,
    survey_date TEXT NOT NULL,
    answers_json TEXT NOT NULL,
    score_avg REAL,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configuration (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'str',
    description TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    data_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
