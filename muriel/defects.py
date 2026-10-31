""" defects: add, resolve, reopen, delete. """
from flask import Blueprint, flash, redirect, url_for

from .auth import login_required
from .constants import SEVERITIES
from .db import get_db
from .forms import field, int_field
from .guards import (get_circuit_or_404, get_defect_or_404, get_job_or_404, refuse_if_locked)

bp = Blueprint("defects", __name__)

def _back(job_id):
    return redirect(url_for("jobs.detail", job_id=job_id, _anchor="defects"))

@bp.post("/jobs/<int:job_id>/defects")
@login_required
def add(job_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    description, severity = field("description", 500), field("severity", 10) or "medium"
    circuit_raw = field("circuit_id", 10)
    if not description:
        flash("Describe the defect.", "error")
        return _back(job_id)
    if severity not in SEVERITIES:
        flash("Choose a severity from the list.", "error")
        return _back(job_id)
    circuit_id = None
    if circuit_raw:
        cid = int_field("circuit_id")
        if cid is None:
            flash("Choose a circuit from the list.", "error")
            return _back(job_id)
        circuit_id = get_circuit_or_404(job, cid)["id"]  # must be a circuit of THIS job.
    db = get_db()
    db.execute("INSERT INTO defects (job_id, circuit_id, description, severity) VALUES (?, ?, ?, ?)",
               (job_id, circuit_id, description, severity))
    db.commit()
    flash("Defect logged.", "ok")
    return _back(job_id)

@bp.post("/jobs/<int:job_id>/defects/<int:defect_id>/resolve")
@login_required
def resolve(job_id, defect_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    get_defect_or_404(job, defect_id)
    db = get_db()
    db.execute("UPDATE defects SET status = 'resolved', resolved_at = datetime('now') "
               "WHERE id = ? AND job_id = ?", (defect_id, job_id))
    db.commit()
    flash("Defect marked resolved.", "ok")
    return _back(job_id)

@bp.post("/jobs/<int:job_id>/defects/<int:defect_id>/reopen")
@login_required
def reopen(job_id, defect_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    get_defect_or_404(job, defect_id)
    db = get_db()
    # resolved_at MUST be cleared: the schema's CHECK refuses 'open' with a timestamp.
    db.execute("UPDATE defects SET status = 'open', resolved_at = NULL "
               "WHERE id = ? AND job_id = ?", (defect_id, job_id))
    db.commit()
    flash("Defect reopened.", "ok")
    return _back(job_id)

@bp.post("/jobs/<int:job_id>/defects/<int:defect_id>/delete")
@login_required
def delete(job_id, defect_id):
    job = get_job_or_404(job_id)
    locked = refuse_if_locked(job)
    if locked:
        return locked
    get_defect_or_404(job, defect_id)
    db = get_db()
    db.execute("DELETE FROM defects WHERE id = ? AND job_id = ?", (defect_id, job_id))
    db.commit()
    flash("Defect deleted.", "ok")
    return _back(job_id)