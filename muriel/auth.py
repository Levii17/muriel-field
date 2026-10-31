""" accounts: register, log in, log out, and the login_required decorator. """
import functools
import sqlite3

from flask import (Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .forms import field

bp = Blueprint("auth", __name__)

# checked when the email is unknown, so "no such user" and "wrong password"
# take about the same time.
_DUMMY_HASH = generate_password_hash("not-a-real-password")

@bp.before_app_request
def load_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
        if g.user is None:
            session.clear()

def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(ok=False, error="Not logged in."), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped

def _start_session(user_id):
    session.clear()  # new session on login: drops any pre-login state.
    session["user_id"] = user_id

@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.user:
        return redirect(url_for("jobs.index"))
    if request.method == "POST":
        name = field("name", 100)
        email = field("email", 200).lower()
        password = request.form.get("password") or ""
        errors = []
        if not name:
            errors.append("Name is required.")
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if len(password) > 200:
            errors.append("Password is too long.")
        if password != (request.form.get("confirm") or ""):
            errors.append("Passwords do not match.")
        if not errors:
            db = get_db()
            try:
                cur = db.execute(
                    "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
                    (email, generate_password_hash(password), name))
                db.commit()
            except sqlite3.IntegrityError:
                errors.append("That email is already registered.")
            else:
                _start_session(cur.lastrowid)
                flash("Welcome! Add a client, then create your first job.", "ok")
                return redirect(url_for("jobs.index"))
        for e in errors:
            flash(e, "error")
        return render_template("register.html", name=name, email=email), 400
    return render_template("register.html", name="", email="")

@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user:
        return redirect(url_for("jobs.index"))
    if request.method == "POST":
        email = field("email", 200).lower()
        password = request.form.get("password") or ""
        user = get_db().execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
        ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password)
        if user and ok:
            _start_session(user["id"])
            return redirect(url_for("jobs.index"))
        flash("Wrong email or password.", "error")
        return render_template("login.html", email=email), 400
    return render_template("login.html", email="")

@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))