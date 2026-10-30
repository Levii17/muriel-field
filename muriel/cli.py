""" 
command-line helpers: flask --app muriel init-db | add-limit | list-limits
no limit values are built into the app.
maybe i'll add some from an applicable standard, with its source using add-limit later.
"""
import os
import sqlite3
import click

from flask import current_app
from flask.cli import with_appcontext

from .constants import PROTECTION_TYPES, canonical_protection_type
from .db import get_db, init_db

@click.command("init-db")
@click.command("--force", is_flag=True, help="Delete the existing database first.")
@with_appcontext
def init_db_command(force):
    """ create the database from schema.sql """
    path = current_app.config["DATABASE"]
    if os.path.exists(path):
        if not force:
            raise click.ClickException(f"{path} already exists. Use --force to start again (delete all data).")
        os.remove(path)
    init_db()
    click.echo(f"Created {path}")

@click.command("add-limit")
@click.option("--test-type", required=True, help="e.g. earth_loop_impedance (see test_types).")
@click.option("--protection-type", default=None, help=f"One of: {', '.join(PROTECTION_TYPES)}. Omit for 'any'.")
@click.option("--rating", type=click.IntRange(min=1), default=None, help="Protection rating in amps. Omit for 'any'.")
@click.option("--value", "limit_value", required=True, type=click.FloatRange(min=0), help="The limit value.")
@click.option("--source", required=True, help="Standard, edition and clause or table the value came from.")
@click.option("--verified",is_flag=True, help="Mark as checked against the standard (default: unverified).")
@with_appcontext
def add_limit_command(test_type, protection_type, rating, limit_value, source, verified):
    """ add one limit row. values must come from the applicable standard. """
    db = get_db()
    if db.execute(
        "SELECT 1 FROM test_types WHERE code = ?",
        (test_type)
    ).fetchone() is None:
        codes = [r["code"] for r in db.execute("SELECT code FROM test_types ORDER BY code")]
        raise click.ClickException(f"Unknown test type. Choose one of: {', '.join(codes)}")
    if protection_type is not None:
        protection_type = canonical_protection_type(protection_type)
        if protection_type is None:
            raise click.ClickException(f"Protection type must be one of: {', '.join(PROTECTION_TYPES)}")
    try:
        db.execute(
            "INSERT INTO test_limits (test_type, protection_type, rating_a, limit_value, source, verified) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (test_type, protection_type, rating, limit_value, source, 1 if verified else 0)
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise click.ClickException(f"Not added: {exc} (a limit for that scope may already exist).")
    click.echo("Limit added" + (" (verified)." if verified else " (unverified)."))

@click.command("list-limits")
@with_appcontext
def list_limits_command():
    """ show every limit row. """
    rows = get_db().execute(
        "SELECT * FROM test_limits ORDER BY test_type, protection_type, rating_a"
    ).fetchall()
    if not rows:
        click.echo("No limits yet. Add them with: flask --app muriel add-limit --help")
    for r in rows:
        click.echo(f"#{r['id']} {r['test_type']} | {r['protection_type'] or 'any'} | "
                   f"#{r['rating_a'] or 'any'} A | {r['limit_value']:g} "
                   f"{'verified' if r['verified'] else 'UNVERIFIED'} | {r['source']}")
