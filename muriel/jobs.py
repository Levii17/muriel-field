""" jobs: dashboard, create, detail, edit, delete, advance, report. """
from flask import (Blueprint, abort, flash, g, redirect, render_template, request, url_for)

from .auth import login_required
from .constants import PROTECTION_TYPES, SEVERITIES, STATUS_LABELS, next_status
from .db import get_db
from .forms import field, int_field
from .guards import get_job_or_404, job_is_editable, refuse_if_locked

bp = Blueprint("jobs", __name__)

# what to SHOW for the client and electrician: the live rows while the job is
# being worked on, the snapshot once it is 'reported. keyed on status rather
# than COALESCE(snapshot, live) so an optional field that was empty when the
# job was finalized (e.g. no phone number) can't pick up a number added later.
JOB_VIEW = """
SELECT j.*
    CASE WHEN j.status = 'reported' THEN j.client_name ELSE c.name END AS client_display,
    CASE WHEN j.status = 'reported' THEN j.client_phone ELSE c.phone END AS client_phone_display,
    CASE WHEN j.status = 'reported' THEN j.client_email ELSE c.email END AS client_email_display,
    CASE WHEN j.status = 'reported' THEN j.reported_by_name ELSE u.name END AS electrician_display
FROM jobs j
JOIN clients c ON c.id = j.client_id
JOIN users u ON u.id = j.user_id
"""

# tested -> reported: ONE statement sets the status AND copies the details
# that appear on the report. (the schema refuses 'reported' without them, and
# the lock trigger only fires when the OLD status is already 'reported')
REPORT_UPDATE = """
UPDATE jobs SET
    status = 'reported',
    updated_at = datetime('now'),
    client_name = (SELECT name FROM clients WHERE id = jobs.client_id),
    client_phone = (SELECT phone FROM clients WHERE id = jobs.client_id),
    client_email = (SELECT email FROM clients WHERE id = jobs.client_id),
    reported_by_name = (SELECT name FROM users WHERE id = jobs.user_id),
WHERE id = ? AND user_id = ? AND status = 'tested'
"""

def _load_job_data(job_id):
    """ everything the detail page and the report need, scoped to this user. """
    db = get_db()
    job = db.execute(
        JOB_VIEW + "WHERE j.id = ? AND j.user_id = ?",
        (job_id, g.user["id"])
    ).fetchone()
    if job is None:
        abort(404)

    circuits = [dict(c, readings=[]) for c in db.execute(
        "SELECT * FROM circuits WHERE job_id = ? ORDER BY id",
        (job_id)
    )]
    by_id = {c["id"]: c for c in circuits}

    readings = db.execute(
        "SELECT r.*, t.label AS test_label, t.unit AS unit FROM readings r "
        "JOIN circuits c ON c.id = r.circuit_id " 
        "JOIN test_types t ON t.code = r.test_type "
        "WHERE c.job_id = ? ORDER BY r.id",
        (job_id)
    ).fetchall()
    for r in readings:
        by_id[r["circuit_id"]]["readings"].append(r)

    defects = db.execute(
        "SELECT d.*, c.name AS circuit_name FROM defects d "
        "LEFT JOIN circuits c ON c.id = d.circuit_id "
        "WHERE d.job_id = ? ORDER BY d.status = 'resolved', d.id ",
        (job_id)
    ).fetchall()

    summary = {
        "pass": sum(r["result"] == "pass" for r in readings),
        "flag": sum(r["result"] == "flag" for r in readings),
        "unchecked": sum(r["result"] == "unchecked" for r in readings),
        "open_defects": sum(d["status"] == "open" for d in defects),
        "unverified_limits": any(r["limit_verified"] == 0 for r in readings),
    }
    return {"job": job, "circuits": circuits, "defects": defects, "summary": summary}

@bp.get("/")
@login_required
def index():
    jobs = get_db().execute(
        """
        SELECT j.id, j.title, j.site_address, j.status, j.created_at,
                CASE WHEN j.status = 'reported' THEN j.client_name ELSE c.name END AS client_display,
                (SELECT COUNT(*) FROM defects d WHERE d.job_id = j.id AND d.status = 'open') AS open_defects
        FROM jobs j JOIN clients c ON c.id = j.client_id
        WHERE j.user_id = ?
        ORDER BY j.created_at DESC, j.id DESC
        """,
        (g.user["id"])
    ).fetchall()
    return render_template("index.html", jobs=jobs, labels=STATUS_LABELS)

@bp.route("/jobs/new", methods=("GET", "POST"))
@login_required
def new():
    db = get_db()
    clients = db.execute(
        "SELECT id, name FROM clients WHERE user_id = ? "
        "ORDER BY name COLLATE NOCASE",
        (g.user["id"])
    ).fetchall()

    if request.method == "POST":
        title, site = field("title", 150), field("site_address", 250)
        client_id = int_field("client_id")
        errors = []
        if not title:
            errors.append("Job title is required.")
        if not site:
            errors.append("Site address is required.")
        # the selected client must belong to the logged-in user. checked here,
        # and again by the composite foreign key on jobs.
        client = None if client_id is None else db.execute(
            "SELECT id FROM clients WHERE Id = ? AND user_id = ?",
            (client_id, g.user["id"])
        ).fetchone()

        if client is None:
            errors.append("Choose one of your clients.")
        if not errors:
            cur = db.execute(
                "INSERT INTO jobs (user_id, client_id, title, site_address) VALUES (?, ?, ?, ?)",
                (g.user["id"], client["id"], title, site)    
            )
            db.commit()
            flash("Job created. ADd its circuits next.", "ok")
            return redirect(url_for("jobs.detail", job_id=cur.lastrowid))
        for e in errors:
            flash(e, "error")
        return render_template("job_new.html", clients=clients, title=title, site=site, client_id=client_id), 400

    if not clients:
        flash("Add a client before creating a job.", "error")
        return redirect(url_for("clients.index"))
    return render_template("job_new.html", clients=clients, title="", site="", client_id=None)

@bp.get("/jobs/<int:job_id>")
@login_required
def detail(job_id):
    data = _load_job_data(job_id)
    db = get_db()
    return render_template(
        "job_detail.html", **data,
        editable=job_is_editable(data["job"]),
        next_stage=next_status(data["job"]["status"]),
        labels=STATUS_LABELS,
        clients=db.execute(
            "SELECT id, name FROM clients WHERE user_id = ? "
            "ORDER BY name COLLATE NOCASE",
            (g.user["id"])
        ).fetchall(),
        test_type=db.execute(
            "SELECT * FROM test_types ORDER BY label"
        ).fetchall(),
        protection_types=PROTECTION_TYPES,
        severities=SEVERITIES
    )