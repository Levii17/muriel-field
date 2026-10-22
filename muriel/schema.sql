-- OWNERSHIP MODEL
--   users -> clients -> jobs   user_id stored on clients and jobs
--   jobs -> circuits -> readings reached only by joining through a job
--   jobs -> defects              (optionally tied to one circuit of that job)
-- Composite foreign keys make the database itself refuse cross-user links
-- (e.g. a job pointing at someone else's client), as a backstop to the
-- ownership checks in the Flask routes.
--
-- Locking: once a job's status is 'reported', the database refuses any insert
-- update or delete on that job's circuits, readings, and defects, and refuses
-- any changes to, or deletion of, the job itself. (triggers at  the end of this file).
-- Client and electrician details are copied onto the job at the
-- moment it becomes 'reported', so the finished report stays frozen. Flask's job_is_editable(job) enforces
-- the same rule earlier, so users get a friendly message instead of a database error.
--
-- Timestamps are UTC text in 'YYYY-MM-DD HH:MM:SS' format.
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- users
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -------------------------------------------------------------- clients
CREATE TABLE clients (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    phone TEXT,
    email TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- Lets jobs reference (client, owner) together.
    UNIQUE (id, user_id)
);
CREATE INDEX idx_clients_user ON clients (user_id, name);

-- ----------------------------------------------------------------- jobs
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id INTEGER NOT NULL,
    title TEXT NOT NULL CHECK (length (trim(title)) > 0),
    site_address TEXT NOT NULL CHECK (length (trim(site_address)) > 0),
    status TEXT NOT NULL DEFAULT 'draft' 
        CHECK (status IN ('draft', 'in_progress', 'tested', 'reported')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        -- Snapshot of who the report is for and who signed it off, NULL until the
        -- job becomes 'reported'; the same UPDATE that sets status = 'reported'
        -- must fill them (the CHECK below refuses it otherwise). After that the
        -- lock trigger stops them changing. Reports read
        -- COALESCE(job.client_name, client.name) etc.
    client_name TEXT,
    client_phone TEXT,
    client_email TEXT,
    reported_by_name TEXT,
    CHECK (status <> 'reported'
        OR (client_name IS NOT NULL AND reported_by_name IS NOT NULL)),
        -- The client must belong to the same user as the job.
        -- RESTRICT: you can't delete a client who still has jobs.
    FOREIGN KEY (client_id, user_id) REFERENCES clients (id, user_id) ON DELETE RESTRICT
);
CREATE INDEX idx_jobs_user_status ON jobs (user_id, status);
CREATE INDEX idx_jobs_client ON jobs (client_id);

-- Status only moves forward, one stage at a time:
--  draft -> in_progress -> tested -> reported. Same-value updates are allowed.
CREATE TRIGGER jobs_status_forward_only 
BEFORE UPDATE OF status ON jobs 
WHEN NEW.status <> OLD.status
 AND (CASE NEW.status
        WHEN 'draft' THEN 1
        WHEN 'in_progress' THEN 2
        WHEN 'tested' THEN 3
        WHEN 'reported' THEN 4
    END) 
 <> (CASE OLD.status
        WHEN 'draft' THEN 1
        WHEN 'in_progress' THEN 2
        WHEN 'tested' THEN 3
        WHEN 'reported' THEN 4
    END) + 1 
 BEGIN
    SELECT RAISE (ABORT, 'Job status can only move forward one stage at a time');
END;

-- ------------------------------------------------------------- circuits
CREATE TABLE circuits (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length (trim(name)) > 0),
    description TEXT,
    protection_type TEXT, -- free text, e.g. 'MCB B', 'RCBO C', 'fuse'
    protection_rating_a INTEGER CHECK (protection_rating_a IS NULL OR protection_rating_a > 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (job_id, name), -- also servers as the index on job_id
    UNIQUE (id, job_id) -- lets defects reference (circuit, job) together
);

-- ----------------------------------------------------------- test_types
-- Small lookup of what can be measured, and which direction is acceptable.
-- Treated as SEED DATA: the app never edits it. Readings snapshot the limit and
-- comparison but not the unit or label, so changing a unit here would change
-- the meaning of old readings. Add new test types; don't alter exisiting ones.
-- 'max' = reading must be <= limit   'min' = reading must be >= limit
CREATE TABLE test_types (
    code TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    unit TEXT NOT NULL,
    comparison TEXT NOT NULL CHECK (comparison IN ('max', 'min'))
);

INSERT INTO test_types (code, label, unit, comparison) VALUES
    (
        'earth_loop_impedance',
        'Earth fault loop impedance (Zs)',
        'ohm',
        'max'
    ),
    (
        'insulation_resistance',
        'Insulation resistance',
        'Mohm',
        'min'
    ),
    (
        'protective_continuity',
        'Protective conductor continuity',
        'ohm',
        'max'
    ),
    (
        'rcd_trip_time', 
        'RCD trip time', 
        'ms', 
        'max'
    )
;

-- ---------------------------------------------------------- test_limits
-- NO LIMIT VALUES ARE SEEDED HERE ON PURPOSE. Take each value from the
-- applicable standard, record the exact source, and only then set verified = 1.
-- protection_type / rating_a may be NULL, meaning "applies to any"
-- when looking up a limit, prefer the most specific matching row.
CREATE TABLE test_limits (
    id INTEGER PRIMARY KEY,
    test_type TEXT NOT NULL REFERENCES test_types(code) ON DELETE RESTRICT,
    protection_type TEXT,
    rating_a INTEGER CHECK (rating_a IS NULL OR rating_a > 0),
    limit_value REAL NOT NULL CHECK (limit_value >= 0),
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- one row per (test, protection_type, rating_a) combination. NULLs treated as "any".
CREATE UNIQUE INDEX uq_test_limits_scope ON test_limits (
    test_type,
    COALESCE(protection_type, ''),
    COALESCE(rating_a, 0)
);

-- ------------------------------------------------------------- readings
-- the limit applied is copied onto the reading (snapshot) so editing the
-- limits table later never silently changes an old report.
CREATE TABLE readings (
    id INTEGER PRIMARY KEY,
    circuit_id INTEGER NOT NULL REFERENCES circuits(id) ON DELETE CASCADE,
    test_type TEXT NOT NULL REFERENCES test_types(code) ON DELETE RESTRICT,
    value REAL NOT NULL,
    limit_id INTEGER REFERENCES test_limits(id) ON DELETE SET NULL,
    limit_comparison TEXT CHECK (limit_comparison IN ('max', 'min')),
    limit_value REAL,
    limit_verified INTEGER CHECK (limit_verified IN (0, 1)),
    result TEXT NOT NULL 
        CHECK (result IN ('pass', 'flag', 'unchecked')),
        -- "flag" rather than "fail": the app doesn't certify.
    notes TEXT,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
        -- a checked reading must carry the lmit it was checked against, including
        -- whether that limit was verified (so the report's "unverified limit" note
        -- can never be skipped by a NULL). an unchecked reading carries none of it.
    CHECK (
        (result = 'unchecked'
            AND limit_value IS NULL AND limit_comparison IS NULL
            AND limit_verified IS NULL)
     OR (result IN ('pass', 'flag')
            AND limit_value IS NOT NULL AND limit_comparison IS NOT NULL
            AND limit_verified IS NOT NULL)
        ),
        -- the stored result must agree with the stored value and limit snapshot,
        -- so a bug in the FLASK calculation can't reach a report.
        -- a reading exactly on the limit passes.
    CHECK (result = 'unchecked'
     OR (limit_comparison = 'max'
         AND result = CASE WHEN value <= limit_value THEN 'pass' ELSE 'flag' END)
     OR (limit_comparison = 'min'
         AND result = CASE WHEN value >= limit_value THEN 'pass' ELSE 'flag' END)
        )
    );
CREATE INDEX idx_readings_circuit ON readings(circuit_id, test_type);

-- -------------------------------------------------------------- defects
CREATE TABLE defects (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    circuit_id INTEGER,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT,
    CHECK (
        (status = 'open' AND resolved_at IS NULL)
     OR (status = 'resolved' AND resolved_at IS NOT NULL)
    ),
    -- if a circuit is given it must belong to the same job.
    -- (not enforced when circuit_id is NULL)
    FOREIGN KEY (circuit_id, job_id) REFERENCES circuits(id, job_id) ON DELETE CASCADE
);
CREATE INDEX idx_defects_job ON defects(job_id, status);
CREATE INDEX idx_defects_circuit ON defects(circuit_id);

-- ---------------------------------------------------------- lock triggers
-- a job is locked when its status is 'reported'. every write to its circuits
-- readings or defects is refused, including resolving or reopening a defect.
-- UPDATE triggers checks both OLD and NEW so a row can't be moved into or out
-- of a locked job.

-- the job itself: without this, DELETE FROM jobs could cascade and wipe a
-- finalized job's circuits, readings, and defects past the triggers below
-- SQLite removes the parent row first, so the child triggers see no locked job.
CREATE TRIGGER jobs_lock_delete
BEFORE DELETE ON jobs
WHEN OLD.status = 'reported'
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported) and cannot be deleted');
END;

-- the job's own fields (title, site, client, snapshot columns). it only fires
-- when the OLD status is 'reported', so the update that moves a job from
-- 'tested' to 'reported' (and fills the snapshot) still passes.
CREATE TRIGGER jobs_lock_update
BEFORE UPDATE ON jobs
WHEN OLD.status = 'reported'
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported) and cannot be changed');
END;

-- circuits (belong directly to a job)
CREATE TRIGGER circuits_lock_insert
BEFORE INSERT ON circuits
WHEN EXISTS (SELECT 1 FROM jobs WHERE id = NEW.job_id AND status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;    

CREATE TRIGGER circuits_lock_update
BEFORE UPDATE ON circuits
WHEN EXISTS (SELECT 1 FROM jobs WHERE id IN (OLD.job_id, NEW.job_id) AND status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;

CREATE TRIGGER circuits_lock_delete
BEFORE DELETE ON circuits
WHEN EXISTS (SELECT 1 FROM jobs WHERE id = OLD.job_id AND status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;

-- readings (reach their job through the circuit)
CREATE TRIGGER readings_lock_insert
BEFORE INSERT ON readings
WHEN EXISTS (SELECT 1 FROM circuits c JOIN jobs j ON j.id = c.job_id 
            WHERE c.id = NEW.circuit_id AND j.status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;

-- one exception: limit_id may go from a value to NULL with every other column
-- unchanged. that is exactly what ON DELETE SET NULL on test_limits does, and
-- without the exception deleting a limit used by any reported job would abort.
-- the snaphot columns are untouched, so the reading itself doesn't change.
CREATE TRIGGER readings_lock_update
BEFORE UPDATE ON readings
WHEN EXISTS (SELECT 1 FROM circuits c JOIN jobs j ON j.id = c.job_id
            WHERE c.id IN (OLD.circuit_id, NEW.circuit_id) AND j.status = 'reported')
    AND NOT (OLD.limit_id IS NOT NULL AND NEW.limit_id IS NULL
             AND NEW.circuit_id = OLD.circuit_id AND NEW.test_type = OLD.test_type
             AND NEW.value = OLD.value AND NEW.result = OLD.result
             AND NEW.limit_comparison IS OLD.limit_comparison
             AND NEW.limit_value IS OLD.limit_value
             AND NEW.limit_verified IS OLD.limit_verified
             AND NEW.notes IS OLD.notes AND NEW.recorded_at = OLD.recorded_at
            )
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;

CREATE TRIGGER readings_lock_delete
BEFORE DELETE ON readings
WHEN EXISTS (SELECT 1 FROM circuits c JOIN jobs j ON j.id = c.job_id
             WHERE c.id = OLD.circuit_id AND j.status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;

-- defects (belong directly to a job)
CREATE TRIGGER defects_lock_insert
BEFORE INSERT ON defects
WHEN EXISTS (SELECT 1 FROM jobs WHERE id = NEW.job_id AND status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;

CREATE TRIGGER defects_lock_update
BEFORE UPDATE ON defects
WHEN EXISTS (SELECT 1 FROM jobs WHERE id IN (OLD.job_id, NEW.job_id) AND status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;

CREATE TRIGGER defects_lock_delete
BEFORE DELETE ON defects
WHEN EXISTS (SELECT 1 FROM jobs WHERE id = OLD.job_id AND status = 'reported')
BEGIN
    SELECT RAISE(ABORT, 'Job is finalized (reported): circuits, readings and defects are locked');
END;