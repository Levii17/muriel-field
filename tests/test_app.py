""" end-to-end tests through the flask routes. """
import pytest

def add_limit(raw, value=1.0, verified=0, **scope):
    """ a TEST-ONLY limit. real values come from the standard via `flask add-limit`. """
    raw.execute(
        "INSERT INTO test_limits (test_type, protection_type, rating_a, limit_value, source, verified) "
        "VALUES (?, ?, ?, ?, 'TEST ONLY', ?)",
        (scope.get("test_type", "earth_loop_impedance"), scope.get("protection_type"),
         scope.get("rating_a"), value, verified))
    raw.commit()

def reading(raw, n=1):
    return raw.execute("SELECT * FROM readings ORDER BY id").fetchall()[n - 1]

def go_to_tested(b, job):
    for _ in range(2):
        b.post(f"/jobs/{job}/advance")
