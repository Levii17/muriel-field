""" clients: list, create, edit. (deleting a client is blocked while jobs use it.) """
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .forms import field, optional
from .guards import get_client_or_404

bp = Blueprint("clients", __name__, url_prefix="/clients")

def _client_form():
    name = field("name", 150)
    if not name:
        flash("Client name is required.", "error")
        return None
    return (name, optional("phone", 50), optional("email", 200), optional("notes", 1000))

@bp.get("/")
@login_required
def index():
    rows = get_db().execute(
        "SELECT c.*, (SELECT COUNT(*) FROM jobs j WHERE j.client_id = c.id) AS job_count "
        "FROM clients c WHERE c.user_id = ? ORDER BY c.name COLLATE NOCASE", 
        (g.user["id"],)
    ).fetchall()
    return render_template("clients.html", clients=rows)

@bp.post("/")
@login_required
def create():
    data = _client_form()
    if data is None:
        return redirect(url_for("clients.index"))
    db = get_db()
    db.execute("INSERT INTO clients (user_id, name, phone, email, notes) VALUES (?, ?, ?, ?, ?)",
               (g.user["id"], *data))
    db.commit()
    flash("Client added.", "ok")
    return redirect(url_for("clients.index"))

@bp.route("/<int:client_id>/edit", methods=("GET", "POST"))
@login_required
def edit(client_id):
    client = get_client_or_404(client_id)
    if request.method == "POST":
        data = _client_form()
        if data is not None:
            db = get_db()
            db.execute("UPDATE clients SET name = ?, phone = ?, email = ?, notes = ? "
                       "WHERE id = ? AND user_id = ?", (*data, client_id, g.user["id"]))
            db.commit()
            flash("Client updated. Jobs already reported keep the details they were finalized with.", "ok")
            return redirect(url_for("clients.index"))
    return render_template("client_edit.html", client=client)