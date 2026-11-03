# muriel Field

a small web app for electricians. it keeps job records in one place: clients, jobs,
circuits, test readings and defects. it then produces a readable inspection report.

muriel field records & flags information. it doesn't certify anything.
reports are labelled as inspection records, not certificates of compliance. limit values are never built in: you enter one from the applicable standard, with its source.

**stack:** flask + jinja, sqlite, vanilla javascript (live reading check only).

## run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt**
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
flask --app muriel init-db
flask --app muriel run --debug
```

open http://127.0.0.1:5000, register, add a client, create a job.

serving over HTTPS: also set `MURIEL_SECURE_COOKIES=1`.

### adding limit values

the app ships with **no** limits. readings for a circuit with no matching limit are saved as `unchecked`. add limits from the standard, one at a time:

```bash
flask --app muriel add-limit --test-type earth_loop_impedance \
  --protection-type "MCB B" --rating 20 --value <value> \
  --source "<standard, edition, clause or table>"
flask --app muriel list-limits
```

new limits start **unverified**. Check the value against the standard, then add `--verified` when you create it. reports show a note whenever a reading used an unverified limit. omit `--protection-type` or `--rating` for a limit that applies to any.

### tests

```bash
python -m pytest
```

`tests/test_schema.py` talks to SQLite directly and proves the database enforces its own rules. `tests/test_app.py` goes through the routes: the whole flow, cross-user access, locking, CSRF, the reading checks.

# layout

```
docs/
    notes.md     decisions and rules, with the reasoning
    project-brief.md
muriel/
    __init__.py   app factory, config, error pages, local-time filter
    schema.sql    tables, CHECKs and triggers (the source of truth for the data rules)
    db.py         one connection per request, foreign keys switched on
    security.py   CSRF token
    auth.py       register, login, logout, login_required
    guards.py     ownership lookups, job_is_editable, refuse_if_locked
    limits.py     limit lookup and the pass/flag calculation
    clients.py  jobs.py  circuits.py  defects.py   the routes
    cli.py        init-db, add-limit, list-limits
    templates/
    static/
tests/
README.md
requirements.txt
```

## routes

all routes except register & login require a logged-in user. every route below that takes a job id, looks the job up by id **&&** the logged-in user, so another user's job is a 404.
circuits, readings & defects are then looked up through that job.
routes marked 🔒 also call `refuse_if_locked(job)` and do nothing on a finalized job.

| method    | path                                    | what it does                                                 |
| --------- | --------------------------------------- | ------------------------------------------------------------ |
| GET, POST | `/register`                             | create an account (password hashed) and log in               |
| GET, POST | `/login`                                | log in                                                       |
| POST      | `/logout`                               | clear the session                                            |
| GET       | `/`                                     | dashboard: my jobs, status, open defect count                |
| GET, POST | `/clients/`                             | list clients; add a client                                   |
| GET, POST | `/clients/<id>/edit`                    | edit a client (finalized jobs keeps their snapshot)          |
| GET, POST | `/jobs/new`                             | create a job: the chosen client must belong to me            |
| GET       | `/jobs/<id>`                            | job page: circuits, readings, defects                        |
| POST      | `/jobs/<id>/edit` 🔒                    | edit title, site, client                                     |
| POST      | `/jobs/<id>/delete` 🔒                  | delete an unfinalized job                                    |
| POST      | `/jobs/<id>/advance`                    | move to the next stage; the browser sends no status          |
| GET       | `/jobs/<id>/report`                     | printable inspection record                                  |
| POST      | `/jobs/<id>/circuits` 🔒                | add a circuit                                                |
| POST      | `/jobs/<id>/circuits/<cid>/edit` 🔒     | edit a circuit                                               |
| POST      | `/jobs/<id>/circuits/<cid>/delete` 🔒   | delete a circuit and its readings                            |
| POST      | `/jobs/<id>/circuits/<cid>/readings` 🔒 | record a reading; the server decides pass, flag or unchecked |
| POST      | `/jobs/<id>/readings/<rid>/delete` 🔒   | delete a reading (typo correction)                           |
| GET       | `/api/jobs/<id>/circuits/<cid>/check`   | json preview of a reading's result; saves nothing            |
| POST      | `/jobs/<id>/defects` 🔒                 | log a defect (general, or on a circuit of this job)          |
| POST      | `/jobs/<id>/defects/<did>/resolve` 🔒   | mark resolved (sets `resolved_at`)                           |
| POST      | `/jobs/<id>/defects/<did>/reopen` 🔒    | reopen (clears `resolved_at`)                                |
| POST      | `/jobs/<id>/defects/<did>/delete` 🔒    | delete a defect                                              |

## design choices

each of these have a fuller explanation in `/docs/notes.md`.

- **why every table is scoped to a user:** ownership lives on `clients` & `jobs`; everything else is reached through a job. composite foreign keys make the database refuse cross-user links as a second line of defense.
- **why the server decides pass or flag:** the browser only previews, through the same python function.
- **why readings store a copy of the limit:** so editing or deleting a limit later never changes an old report.
- **why `flag` and not `fail`:** the app doesn't certify anything.
- **why status only moves forward, and the browser never sends it:** stage order is enforced by a trigger & by the advance route reading the stored status.
- **why a `reported` job is locked, in the app & in the database:** the report is the frozen record. `job_is_editable` gives a friendly message; the triggers catch anything a route misses.
- **why client & electrician details are copied onto the job when it's reported:** same idea as the limit snapshot: later edits to a client must not rewrite the finished report.
- **why `test_types` is seed data:** readings keep the limit and its direction, not the unit or label, so editing a unit would change what old readings mean.

## security basics in this app

passwords hashed with `werkzeug.security`; session reset on login; CSRF token on every POST; parameterized SQL only; HttpOnly & SameSite cookies; every query scoped to the logged-in user; limit values and results validate on the server.

## non-goals

offline mode or syncing, multiple user roles, multi-company support, photo uploads, digital signatures, payments, mobile apps, and **account (user) deletion**.

additionally: materials and costs, PDF export.

## known limits

no login rate limiting. no password reset. clients can't be deleted. readings can't be edited, only deleted & re-entered while the job is active.
