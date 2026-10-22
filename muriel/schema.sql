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
CREATE INDEX idx_clients_user ON clients(user_id, name);

-- ----------------------------------------------------------------- jobs
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id INTEGER NOT NULL,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    site_address TEXT NOT NULL CHECK (length(trim(site_address)) > 0),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'in_progress', 'tested', 'reported')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    update_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- Snapshot of who the report is for and who signed it off, NULL until the
    -- job becomes 'reported'; the same UPDATE that sets status = 'reported'
    -- must fill them (the CHECK below refuses it otherwise). After that the
    -- lock trigger stops them changing. Reports read
    -- COALESCE(job.client_name, client.name) etc.
    client_name TEXT,
    client_phone TEXT,
    client_email TEXT,
    reported_by_name TEXT,
    CHECK (status <> 'reported' OR (client_name IS NOT NULL AND reported_by_name IS NOT NULL)),
    -- The client must belong to the same user as the job.
    -- RESTRICT: you can't delete a client who still has jobs.
    FOREIGN KEY (client_id, user_id) REFERENCES clients(id, user_id) ON DELETE RESTRICT
);
CREATE INDEX idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX idx_jobs_client ON jobs(client_id);

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
    END) +  1
BEGIN
    SELECT RAISE(ABORT, 'Job status can only move forward one stage at a time');
END;
