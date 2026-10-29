"""circuits and readings, plus the JSON endpoint behind the live check."""
import sqlite3

from flask import (Blueprint, flash, g, jsonify, redirect, request, url_for) 

from .auth import login_required
from .constants import canonical_protection_type
from .db import get_db
from .forms import field, int_field, optional
from .guards import (get_circuit_or_404, get_job_or_404, get_reading_or_404, refuse_if_locked)
from .limits import check_reading, describe, get_test_type, parse_value

bp = Blueprint("circuits", __name__)

def _back(job_id, anchor=None):
    return redirect(url_for("jobs.detail", job_id=job_id, _anchor=anchor))

def _circuit_form():
    """ validated (name, description, protection_type, rating) or None. """
    name = field("name", 100)
    ptype_raw, rating_raw = field("protection_type", 50), field("protection_rating_a", 10)
    ptype = canonical_protection_type(ptype_raw) if ptype_raw else None
    rating = int_field("protection_rating_a") if rating_raw else None
    problems = []
    if not name:
        problems.append("Circuit name is required.")
    if ptype_raw and ptype is None:
        problems.append("Choose a protection type from the list.")
    if rating_raw and (rating is None or rating <= 0):
        problems.append("Protection rating must be a whole number of amps above zero.")
    for p in problems:
        flash(p, "error")
    return None if problems else (name, optional("description", 500), ptype, rating)

def _duplicate_or_raise(exc):
    if "UNIQUE" in str(exc):
        flash("A circuit with the name already exists on this job.", "error")
    else:
        raise exc

@bp.post("/jobs/<int:job_id>/circuits")
@login_required
def add_circuit(job_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    data = _circuit_form()
    if data:
        db = get_db()
        try:
            db.execute("INSERT INTO circuits (job_id, name, description, protection_type, " 
                       "protection_rating_a) VALUES (?, ?, ?, ?, ?)", (job_id, *data))
            db.commit()
            flash("Circuit added.", "ok")
        except sqlite3.IntegrityError as exc:
            _duplicate_or_raise(exc)
    return _back(job_id, "circuits")

@bp.post("/jobs/<int:job_id>/circuits/<int:circuit_id>/edit")
@login_required
def edit_circuit(job_id, circuit_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    get_circuit_or_404(job, circuit_id)
    data = _circuit_form()
    if data:
        db = get_db()
        try:
            db.execute(
                "UPDATE circuits SET name = ?, description = ?, protection_type = ?, "
                "protection_rating_a = ? WHERE id = ? AND job_id = ?",
                (*data, circuit_id, job_id)
            )
            db.commit()
            flash("Circuit updated. Existing readings keep the limit they were checked against.", "ok")
        except sqlite3.IntegrityError as exc:
            _duplicate_or_raise(exc)
    return _back(job_id, f"circuit-{circuit_id}")

@bp.post("/jobs/<int:job_id>/circuits/<int:circuit_id/delete")
@login_required
def delete_circuit(job_id, circuit_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    get_circuit_or_404(job, circuit_id)
    db = get_db()
    db.execute(
        "DELETE FROM circuits WHERE id = ? AND job_id = ?",
        (circuit_id, job_id)
    )
    db.commit()
    flash("Circuit deleted, along with its readings.", "ok")
    return _back(job_id, "circuits")

@bp.post("/jobs/<int:job_id>/circuits/<int:circuit_id>/readings")
@login_required
def add_reading(job_id, circuit_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    circuit = get_circuit_or_404(job, circuit_id)
    db = get_db()
    test_type = get_test_type(db, field("test_type", 50))
    if test_type is None:
        flash("Choose a test type.", "error")
        return _back(job_id, f"circuit-{circuit_id}")
    try:
        value = parse_value(request.form.get("value"))
    except ValueError as exc:
        flash(str(exc), "error")
        return _back(job_id, f"circuit-{circuit_id}")

    # the server decides pass/flag, and stores the limit if used (the snapshot).
    check = check_reading(db, circuit, test_type, value)
    db.execute(
        "INSERT INTO readings (circuit_id, test_type, value, limit_id, limit_comparison, "
        "limit_value, limit_verified, result, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (circuit_id, test_type["code"], value, check["limit_id"], check["limit_comparison"], 
         check["limit_Value"], check["limit_verified"], check["result"], optional("notes", 300))
    )
    db.commit()
    category = "error" if check["result"] == "flag" else "ok"
    flash(f"Reading saved: {describe(check, test_type)}", category)
    return _back(job_id, f"circuit-{circuit_id}")

@bp.post("/jobs/<int:job_id>/readings/<int:reading_id>/delete")
@login_required
def delete_reading(job_id, reading_id):
    """ typo correction: delete the reading and enter it again. """
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    reading = get_reading_or_404(job, reading_id)
    db = get_db()
    db.execute(
        "DELETE FROM readings WHERE id = ?",
        (reading_id)
    )
    db.commit()
    flash("Reading deleted. Enter it again if it was a typing mistake.", "ok")
    return _back(job_id, f"circuit-{reading['circuit_id']}")

@bp.get("/api/jobs/<int:job_id>/circuits/<int:circuit_id>/check")
@login_required
def live_check(job_id, circuit_id):
    """ preview only. nothing is saved; uses the same function as add_reading. """
    job = get_job_or_404(job_id)
    circuit = get_circuit_or_404(job, circuit_id)
    db = get_db()
    test_type = get_test_type(db, request.args.get("test_type", ""))
    if test_type is None:
        return jsonify(ok=False, error="Choose a test type."), 400
    try:
        value = parse_value(request.args.get("value"))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    check = check_reading(db, circuit, test_type, value)
    return jsonify(ok=True, result=check["result"], message=describe(check, test_type),
                   verified=check["limit_verified"])