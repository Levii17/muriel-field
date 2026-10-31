"""
reading checks. pure logic shared by the form submit and the live-check
endpoint, so the browser preview can never disagree with what gets saved.
the result is computed here, on the server, at save time. JavaScript only
asks this module (via the JSON endpoint) for a preview.
"""
import math

def parse_value(raw):
    """parse a reading typed by the user. raises ValueError with a message."""
    try:
        value = float((raw or "").strip())
    except ValueError:
        raise ValueError("Enter the reading as a number.") from None
    if not math.isfinite(value):
        raise ValueError("Enter the reading as a number.")
    if value < 0:
        raise ValueError("A reading cannot be negative. Check for a typing mistake.")
    return value + 0.0  # turns -0.0 into 0.0

def evaluate(value, comparison, limit_value):
    """
    'pass' or 'flag'. a reading exactly on the limit passes.
    must match the CHECK constraint on readings.result in schema.sql.
    """
    ok = value <= limit_value if comparison == "max" else value >= limit_value
    return "pass" if ok else "flag"

def get_test_type(db, code):
    return db.execute("SELECT * FROM test_types WHERE code = ?", (code,)).fetchone()

def find_limit(db, test_type, protection_type, rating_a):
    """
    most specific matching limit row, or None.
    a limit row matches when its test type matches and its protection type and
    rating are either NULL ("any") or equal to the circuit's. protection types
    compare case-insensitively. among matches, prefer a row that names both,
    then one that names the rating, then the lowest id.
    """
    return db.execute(
        """
        SELECT * FROM test_limits
        WHERE test_type = :t
          AND (protection_type IS NULL
               OR lower(trim(protection_type)) = lower(trim(:p)))
          AND (rating_a IS NULL OR rating_a = :r)
        ORDER BY (protection_type IS NOT NULL) + (rating_a IS NOT NULL) DESC,
                 (rating_a IS NOT NULL) DESC,
                 id
        LIMIT 1
        """,
        {"t": test_type["code"], "p": protection_type, "r": rating_a},
    ).fetchone()

def check_reading(db, circuit, test_type, value):
    """ 
    look up the limit for this circuit and test, and compute the result.
    returns the exact values to store on the reading, including the snapshot
    of the limit as it is right now.
    """
    limit = find_limit(db, test_type, circuit["protection_type"], circuit["protection_rating_a"])
    if limit is None:
        return {"result": "unchecked", "limit_id": None, "limit_comparison": None,
                "limit_value": None, "limit_verified": None}
    return {
        "result": evaluate(value, test_type["comparison"], limit["limit_value"]),
        "limit_id": limit["id"],
        "limit_comparison": test_type["comparison"],
        "limit_value": limit["limit_value"],
        "limit_verified": limit["verified"],
    }

def symbol(comparison):
    return "\u2264" if comparison == "max" else "\u2265"

def describe(check, test_type):
    if check["result"] == "unchecked":
        return ("No limit on file for this circuit's protection, "
                "so this reading will be saved unchecked.")
    rule = f"must be {symbol(check['limit_comparison'])} {check['limit_value']:g} {test_type['unit']}"
    text = ("Within limit: " if check["result"] == "pass" else "FLAG: ") + rule
    if not check["limit_verified"]:
        text += " (this limit has not been verified against the standard yet)"
    return text