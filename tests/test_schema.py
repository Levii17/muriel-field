""" database-level tests: constraints and triggers in schema.sql, with no flask involved.

each test talks straight to SQLite. the point is to prove the DATABASE refuses
bad data on its own, so a bug in a route can't get past it.

disclaimer: this test suite was written by Claude (Anthropic)

"""
import sqlite3
from pathlib import Path

import pytest

SCHEMA = Path(__file__).parent.parent / "muriel" / "schema.sql"

# ------------------------------------------------------------------ fixtures

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA.read_text())
    # SQLite ignores foreign keys unless this is set on EVERY connection.
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()

# ------------------------------------------------------------------- helpers

def add_user(c, email="luu@example.com", name="Luu"):
    return c.execute("INSERT INTO users (email, password_hash, name) VALUES (?, 'x', ?)",
                     (email, name)).lastrowid

def add_client(c, user_id, name="Ona"):
    return c.execute("INSERT INTO clients (user_id, name) VALUES (?, ?)", (user_id, name)).lastrowid

def add_job(c, user_id, client_id, title="Kitchen DB"):
    return c.execute("INSERT INTO jobs (user_id, client_id, title, site_address) "
                     "VALUES (?, ?, ?, '1 Test Street')", (user_id, client_id, title)).lastrowid

def add_circuit(c, job_id, name="Sockets"):
    return c.execute("INSERT INTO circuits (job_id, name, protection_type, protection_rating_a) "
                     "VALUES (?, ?, 'MCB B', 20)", (job_id, name)).lastrowid

def add_limit(c, value=1.0, test_type="earth_loop_impedance", protection_type=None, rating_a=None):
    return c.execute("INSERT INTO test_limits (test_type, protection_type, rating_a, limit_value, source) "
                     "VALUES (?, ?, ?, ?, 'TEST ONLY')", (test_type, protection_type, rating_a, value)).lastrowid

def add_reading(c, circuit_id, value=0.5, limit_id=None, limit_value=1.0, comparison="max",
                verified=0, result="pass", test_type="earth_loop_impedance"):
    return c.execute(
        "INSERT INTO readings (circuit_id, test_type, value, limit_id, limit_comparison, "
        "limit_value, limit_verified, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (circuit_id, test_type, value, limit_id, comparison, limit_value, verified, result)).lastrowid

def add_defect(c, job_id, circuit_id=None, description="Loose neutral"):
    return c.execute("INSERT INTO defects (job_id, circuit_id, description) VALUES (?, ?, ?)",
                     (job_id, circuit_id, description)).lastrowid

def advance(c, job_id, status):
    c.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))

def finalize(c, job_id):
    """ draft -> reported the way the app does it: the snapshot is filled in the same UPDATE."""
    advance(c, job_id, "in_progress")
    advance(c, job_id, "tested")
    c.execute("UPDATE jobs SET status = 'reported', "
              "client_name = (SELECT name FROM clients WHERE id = jobs.client_id), "
              "reported_by_name = (SELECT name FROM users WHERE id = jobs.user_id) WHERE id = ?",
              (job_id,))

@pytest.fixture
def world(conn):
    """ one user, client, job, circuit, limit, a passing reading, and a defect on the circuit. """
    user = add_user(conn)
    client = add_client(conn, user)
    job = add_job(conn, user, client)
    circuit = add_circuit(conn, job)
    limit = add_limit(conn, 1.0)
    reading = add_reading(conn, circuit, 0.5, limit_id=limit)
    defect = add_defect(conn, job, circuit)
    conn.commit()
    return dict(user=user, client=client, job=job, circuit=circuit, limit=limit,
                reading=reading, defect=defect)

@pytest.fixture
def locked(conn, world):
    """ the same world, with the job finalized. """
    finalize(conn, world["job"])
    conn.commit()
    return world

# ------------------------------------------------------------------- basics

def test_foreign_keys_are_on(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

def test_seeded_test_types(conn):
    rows = {r["code"]: r["comparison"] for r in conn.execute("SELECT * FROM test_types")}
    assert rows == {
        "earth_loop_impedance": "max",
        "insulation_resistance": "min",
        "protective_continuity": "max",
        "rcd_trip_time": "max",
    }

def test_no_limits_are_seeded(conn):
    assert conn.execute("SELECT COUNT(*) FROM test_limits").fetchone()[0] == 0

def test_email_is_unique_ignoring_case(conn):
    add_user(conn, "luu@example.com")
    with pytest.raises(sqlite3.IntegrityError):
        add_user(conn, "LUU@Example.com")

@pytest.mark.parametrize("sql", [
    "INSERT INTO clients (user_id, name) VALUES (1, '   ')",
    "INSERT INTO jobs (user_id, client_id, title, site_address) VALUES (1, 1, '  ', 'x')",
    "INSERT INTO jobs (user_id, client_id, title, site_address) VALUES (1, 1, 'x', '')",
    "INSERT INTO circuits (job_id, name) VALUES (1, ' ')",
])
def test_blank_required_text_is_refused(conn, world, sql):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)

# --------------------------------------------------------------- job status

def test_status_walks_forward_one_stage_at_a_time(conn, world):
    for stage in ("in_progress", "tested"):
        advance(conn, world["job"], stage)
        assert conn.execute("SELECT status FROM jobs").fetchone()[0] == stage

@pytest.mark.parametrize("start, target", [
    ("draft", "tested"),
    ("draft", "reported"),
    ("in_progress", "reported"),
    ("in_progress", "draft"),
    ("tested", "in_progress"),
])
def test_status_cannot_skip_or_go_back(conn, world, start, target):
    path = ["draft", "in_progress", "tested"]
    for stage in path[1:path.index(start) + 1]:
        advance(conn, world["job"], stage)
    with pytest.raises(sqlite3.IntegrityError, match="forward one stage"):
        advance(conn, world["job"], target)

def test_same_status_update_is_allowed(conn, world):
    advance(conn, world["job"], "draft")

def test_unknown_status_is_refused(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        advance(conn, world["job"], "finished")

def test_reported_requires_the_snapshot(conn, world):
    advance(conn, world["job"], "in_progress")
    advance(conn, world["job"], "tested")
    with pytest.raises(sqlite3.IntegrityError):
        advance(conn, world["job"], "reported")

def test_finalizing_copies_client_and_electrician_names(conn, world):
    finalize(conn, world["job"])
    job = conn.execute("SELECT * FROM jobs").fetchone()
    assert (job["status"], job["client_name"], job["reported_by_name"]) == ("reported", "Ona", "Luu")

# --------------------------------------------------------------- ownership

def test_job_cannot_point_at_another_users_client(conn, world):
    other = add_user(conn, "khanzy@example.com", "Khanzy")
    with pytest.raises(sqlite3.IntegrityError):
        add_job(conn, other, world["client"])

def test_client_with_jobs_cannot_be_deleted(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM clients WHERE id = ?", (world["client"],))

def test_defect_cannot_use_a_circuit_from_another_job(conn, world):
    other_job = add_job(conn, world["user"], world["client"], "Second job")
    with pytest.raises(sqlite3.IntegrityError):
        add_defect(conn, other_job, world["circuit"])

def test_defect_without_a_circuit_is_allowed(conn, world):
    add_defect(conn, world["job"], None, "General: no labels on the board")

def test_circuit_names_are_unique_per_job_only(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        add_circuit(conn, world["job"], "Sockets")
    other_job = add_job(conn, world["user"], world["client"], "Second job")
    add_circuit(conn, other_job, "Sockets")

# -------------------------------------------------------------------- limits

def test_limit_scope_is_unique_with_nulls_as_any(conn):
    add_limit(conn, 1.0)
    with pytest.raises(sqlite3.IntegrityError):
        add_limit(conn, 2.0)
    add_limit(conn, 2.0, protection_type="MCB B")
    add_limit(conn, 3.0, protection_type="MCB B", rating_a=20)
    with pytest.raises(sqlite3.IntegrityError):
        add_limit(conn, 4.0, protection_type="MCB B", rating_a=20)

@pytest.mark.parametrize("kwargs", [
    dict(value=-1),
    dict(rating_a=0),
    dict(test_type="not_a_test"),
])
def test_bad_limits_are_refused(conn, kwargs):
    with pytest.raises(sqlite3.IntegrityError):
        add_limit(conn, **kwargs)

def test_limit_needs_a_source(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO test_limits (test_type, limit_value, source) "
                     "VALUES ('rcd_trip_time', 300, '  ')")

# ------------------------------------------------------------------ readings

@pytest.mark.parametrize("comparison, value, limit, expected", [
    ("max", 0.5, 1.0, "pass"),
    ("max", 1.0, 1.0, "pass"),   # exactly on the limit passes
    ("max", 1.5, 1.0, "flag"),
    ("min", 500, 1.0, "pass"),
    ("min", 1.0, 1.0, "pass"),
    ("min", 0.5, 1.0, "flag"),
])
def test_result_must_agree_with_value_and_limit(conn, world, comparison, value, limit, expected):
    wrong = "flag" if expected == "pass" else "pass"
    add_reading(conn, world["circuit"], value, limit_value=limit, comparison=comparison, result=expected)
    with pytest.raises(sqlite3.IntegrityError):
        add_reading(conn, world["circuit"], value, limit_value=limit, comparison=comparison, result=wrong)

def test_unchecked_reading_carries_no_limit(conn, world):
    conn.execute("INSERT INTO readings (circuit_id, test_type, value, result) "
                 "VALUES (?, 'rcd_trip_time', 30, 'unchecked')", (world["circuit"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO readings (circuit_id, test_type, value, limit_value, result) "
                     "VALUES (?, 'rcd_trip_time', 30, 300, 'unchecked')", (world["circuit"],))

@pytest.mark.parametrize("missing", ["limit_value", "limit_comparison", "limit_verified"])
def test_checked_reading_must_carry_the_whole_snapshot(conn, world, missing):
    snapshot = {"limit_value": 1.0, "limit_comparison": "max", "limit_verified": 0}
    snapshot[missing] = None
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO readings (circuit_id, test_type, value, limit_comparison, limit_value, "
            "limit_verified, result) VALUES (?, 'earth_loop_impedance', 0.5, ?, ?, ?, 'pass')",
            (world["circuit"], snapshot["limit_comparison"], snapshot["limit_value"],
             snapshot["limit_verified"]))

def test_reading_needs_a_known_test_type(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        add_reading(conn, world["circuit"], test_type="made_up")

def test_reading_keeps_its_snapshot_when_the_limit_is_edited(conn, world):
    conn.execute("UPDATE test_limits SET limit_value = 0.1 WHERE id = ?", (world["limit"],))
    row = conn.execute("SELECT limit_value, result FROM readings").fetchone()
    assert (row["limit_value"], row["result"]) == (1.0, "pass")

def test_deleting_a_limit_keeps_the_readings_snapshot(conn, world):
    conn.execute("DELETE FROM test_limits WHERE id = ?", (world["limit"],))
    row = conn.execute("SELECT limit_id, limit_value, result FROM readings").fetchone()
    assert (row["limit_id"], row["limit_value"], row["result"]) == (None, 1.0, "pass")

# ------------------------------------------------------------------- defects

def test_open_defect_cannot_have_a_resolved_time(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE defects SET resolved_at = datetime('now') WHERE id = ?", (world["defect"],))

def test_resolved_defect_needs_a_resolved_time(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE defects SET status = 'resolved' WHERE id = ?", (world["defect"],))
    conn.execute("UPDATE defects SET status = 'resolved', resolved_at = datetime('now') WHERE id = ?",
                 (world["defect"],))
    conn.execute("UPDATE defects SET status = 'open', resolved_at = NULL WHERE id = ?", (world["defect"],))

def test_defect_severity_must_be_on_the_list(conn, world):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE defects SET severity = 'catastrophic' WHERE id = ?", (world["defect"],))

# ----------------------------------------------------------------- cascades

def test_deleting_a_draft_job_removes_everything_under_it(conn, world):
    conn.execute("DELETE FROM jobs WHERE id = ?", (world["job"],))
    for table in ("circuits", "readings", "defects"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

def test_deleting_a_circuit_removes_its_readings_and_defects(conn, world):
    conn.execute("DELETE FROM circuits WHERE id = ?", (world["circuit"],))
    assert conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM defects").fetchone()[0] == 0

# ----------------------------------------------------------- the lock: blocked

LOCK_MESSAGE = "finalized"

@pytest.mark.parametrize("sql", [
    "UPDATE jobs SET title = 'changed' WHERE id = :job",
    "UPDATE jobs SET client_name = 'someone else' WHERE id = :job",
    "UPDATE jobs SET status = 'tested' WHERE id = :job",
    "DELETE FROM jobs WHERE id = :job",
    "INSERT INTO circuits (job_id, name) VALUES (:job, 'New circuit')",
    "UPDATE circuits SET name = 'renamed' WHERE id = :circuit",
    "DELETE FROM circuits WHERE id = :circuit",
    "INSERT INTO readings (circuit_id, test_type, value, result) "
    "VALUES (:circuit, 'rcd_trip_time', 30, 'unchecked')",
    "UPDATE readings SET notes = 'edited' WHERE id = :reading",
    "UPDATE readings SET limit_id = NULL, notes = 'edited' WHERE id = :reading",
    "DELETE FROM readings WHERE id = :reading",
    "INSERT INTO defects (job_id, description) VALUES (:job, 'New defect')",
    "UPDATE defects SET status = 'resolved', resolved_at = datetime('now') WHERE id = :defect",
    "UPDATE defects SET description = 'edited' WHERE id = :defect",
    "DELETE FROM defects WHERE id = :defect",
])
def test_reported_job_refuses_every_write(conn, locked, sql):
    with pytest.raises(sqlite3.IntegrityError, match=LOCK_MESSAGE):
        conn.execute(sql, locked)

def test_a_row_cannot_be_moved_into_a_reported_job(conn, locked):
    open_job = add_job(conn, locked["user"], locked["client"], "Still open")
    open_circuit = add_circuit(conn, open_job, "Lights")
    with pytest.raises(sqlite3.IntegrityError, match=LOCK_MESSAGE):
        conn.execute("UPDATE circuits SET job_id = ? WHERE id = ?", (locked["job"], open_circuit))
    with pytest.raises(sqlite3.IntegrityError, match=LOCK_MESSAGE):
        conn.execute("UPDATE readings SET circuit_id = ? WHERE id = ?", (open_circuit, locked["reading"]))

def test_blocked_writes_change_nothing(conn, locked):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM jobs WHERE id = ?", (locked["job"],))
    counts = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("jobs", "circuits", "readings", "defects")]
    assert counts == [1, 1, 1, 1]

# ------------------------------------------------------ the lock: not too broad

def test_draft_job_can_still_be_changed(conn, world):
    conn.execute("UPDATE jobs SET title = 'changed' WHERE id = ?", (world["job"],))
    conn.execute("UPDATE circuits SET name = 'renamed' WHERE id = ?", (world["circuit"],))
    conn.execute("UPDATE readings SET notes = 'edited' WHERE id = ?", (world["reading"],))
    conn.execute("UPDATE defects SET description = 'edited' WHERE id = ?", (world["defect"],))
    conn.execute("DELETE FROM defects WHERE id = ?", (world["defect"],))

def test_locking_one_job_does_not_lock_another(conn, locked):
    other_job = add_job(conn, locked["user"], locked["client"], "Second job")
    other_circuit = add_circuit(conn, other_job, "Lights")
    add_reading(conn, other_circuit)
    add_defect(conn, other_job, other_circuit)
    conn.execute("DELETE FROM jobs WHERE id = ?", (other_job,))

# ----------------------------------------------- the lock: the one exception

def test_deleting_a_limit_used_by_a_reported_job_is_allowed(conn, locked):
    before = dict(conn.execute("SELECT * FROM readings WHERE id = ?", (locked["reading"],)).fetchone())
    conn.execute("DELETE FROM test_limits WHERE id = ?", (locked["limit"],))
    after = dict(conn.execute("SELECT * FROM readings WHERE id = ?", (locked["reading"],)).fetchone())
    assert after.pop("limit_id") is None
    assert before.pop("limit_id") == locked["limit"]
    assert after == before   # every other column, snapshot included, is untouched

def test_editing_a_limit_used_by_a_reported_job_changes_no_reading(conn, locked):
    before = dict(conn.execute("SELECT * FROM readings").fetchone())
    conn.execute("UPDATE test_limits SET limit_value = 0.01, verified = 1 WHERE id = ?", (locked["limit"],))
    assert dict(conn.execute("SELECT * FROM readings").fetchone()) == before
