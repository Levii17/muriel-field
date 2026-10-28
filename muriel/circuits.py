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