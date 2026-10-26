"""
accounts: register, log in, log out, and the login_required decorator.
"""
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
            "SELECT id, email, name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
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
    session.clear() # new session on login: drops any pre-login state.
    session["user_id"] = user_id
    
