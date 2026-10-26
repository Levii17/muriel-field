"""
muriel field: keep electrical inspection records & produce a readable report.
the app records and flags information. it doesn't certify anything.
"""
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, render_template

# SA has no daylight saving time, so a fixed +02:00 offset is enough
# to turn the stored UTC timestamps into local time for display and printing.
LOCAL_OFFSET = timedelta(hours=2)

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    secret = os.environ.get("SECRET_KEY")
    app.config.from_mapping(
        SECRET_KEY=secret or secrets.token_hex(32),
        DATABASE=os.path.join(app.instance_path, "muriel.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # set MURIEL_SECURE_COOKIES=1 when serving over HTTPS
        SESSION_COOKIE_SECURE=os.environ.get("MURIEL_SECURE_COOKIES") == "1",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    elif not secret:
        app.logger.warning("SECRET_KEY is not set: using a random key, so logins reset on restart.")
    os.makedirs(app.instance_path, exist_ok=True)