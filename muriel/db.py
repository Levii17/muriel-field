"""sqlite connection handling: one connection per request."""
import sqlite3 
from pathlib import Path
from flask import current_app, g

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        # sqlite ignores foreign keys unless this is set on every connection.
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close() # anything not committed is rolled back.

def init_db():
    """create all tables, triggers and seed test types from schema.sql"""
    get_db().executescript(Path(__file__).with_name("schema.sql").read_text())

def init_app(app):
    app.teardown_appcontext(close_db)