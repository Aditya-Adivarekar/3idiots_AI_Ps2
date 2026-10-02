CREATE TABLE IF NOT EXISTS data_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT,
    jurisdiction TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS scholarships (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    organization TEXT,
    source_id TEXT,
    source_type TEXT,
    url TEXT,
    description TEXT,
    eligibility TEXT,
    amount TEXT,
    category TEXT,
    state TEXT,
    course_level TEXT,
    gender TEXT,
    income_band TEXT,
    deadline TEXT,
    document_hash TEXT,
    raw_text TEXT,
    fetched_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(source_id) REFERENCES data_sources(id)
);

CREATE INDEX IF NOT EXISTS idx_scholarships_title ON scholarships(title);
CREATE INDEX IF NOT EXISTS idx_scholarships_org ON scholarships(organization);
CREATE INDEX IF NOT EXISTS idx_scholarships_state ON scholarships(state);
CREATE INDEX IF NOT EXISTS idx_scholarships_category ON scholarships(category);

CREATE VIRTUAL TABLE IF NOT EXISTS scholarships_fts USING fts5(
    id,
    title,
    organization,
    description,
    eligibility,
    raw_text,
    content='scholarships',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS scholarships_ai AFTER INSERT ON scholarships BEGIN
    INSERT INTO scholarships_fts(rowid, id, title, organization, description, eligibility, raw_text)
    VALUES (new.rowid, new.id, new.title, new.organization, new.description, new.eligibility, new.raw_text);
END;

CREATE TRIGGER IF NOT EXISTS scholarships_ad AFTER DELETE ON scholarships BEGIN
    INSERT INTO scholarships_fts(scholarships_fts, rowid, id, title, organization, description, eligibility, raw_text)
    VALUES('delete', old.rowid, old.id, old.title, old.organization, old.description, old.eligibility, old.raw_text);
END;

CREATE TRIGGER IF NOT EXISTS scholarships_au AFTER UPDATE ON scholarships BEGIN
    INSERT INTO scholarships_fts(scholarships_fts, rowid, id, title, organization, description, eligibility, raw_text)
    VALUES('delete', old.rowid, old.id, old.title, old.organization, old.description, old.eligibility, old.raw_text);
    INSERT INTO scholarships_fts(rowid, id, title, organization, description, eligibility, raw_text)
    VALUES (new.rowid, new.id, new.title, new.organization, new.description, new.eligibility, new.raw_text);
END;

CREATE TABLE IF NOT EXISTS scholarship_rule_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_id TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_name TEXT,
    version INTEGER NOT NULL CHECK(version > 0),
    field TEXT NOT NULL,
    operator TEXT NOT NULL,
    value_json TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    required INTEGER NOT NULL DEFAULT 1,
    condition_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_updated_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    withdrawn_at TEXT,
    UNIQUE(scheme_id, rule_key, source_url, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_versions_current_source
    ON scholarship_rule_versions(scheme_id, rule_key, source_url)
    WHERE is_current = 1;
CREATE INDEX IF NOT EXISTS idx_rule_versions_current_key
    ON scholarship_rule_versions(scheme_id, rule_key, is_current);
