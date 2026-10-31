"""
muriel Field: keep electrical inspection records and produce a readable report.
the app records and flags information. it doesn't certify anything.
"""
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template

from . import auth, circuits, clients, db, defects, jobs, security
from .cli import add_limit_command, init_db_command, list_limits_command

# south africa has no daylight saving time, so a fixed +02:00 offset is enough
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
        # set MURIEL_SECURE_COOKIES=1 when serving over HTTPS.
        SESSION_COOKIE_SECURE=os.environ.get("MURIEL_SECURE_COOKIES") == "1",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    elif not secret:
        app.logger.warning("SECRET_KEY is not set: using a random key, so logins reset on restart.")
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    security.init_app(app)
    for blueprint in (auth.bp, clients.bp, jobs.bp, circuits.bp, defects.bp):
        app.register_blueprint(blueprint)
    for command in (init_db_command, add_limit_command, list_limits_command):
        app.cli.add_command(command)

    @app.template_filter("localtime")
    def localtime(value, fmt="%d %b %Y, %H:%M"):
        if not value:
            return ""
        return (datetime.strptime(value, "%Y-%m-%d %H:%M:%S") + LOCAL_OFFSET).strftime(fmt)

    @app.errorhandler(400)
    @app.errorhandler(404)
    def http_error(error):
        message = error.description if error.code == 400 else "That page does not exist."
        return render_template("error.html", code=error.code, message=message), error.code

    @app.errorhandler(sqlite3.IntegrityError)
    def database_refused(error):
        app.logger.warning("Database refused a change: %s", error)
        return render_template(
            "error.html", code=409,
            message="The database refused that change (for example, the job may be finalized)."), 409
    return app
