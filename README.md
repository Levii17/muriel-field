# muriel Field

a small web app for electricians. it keeps job records in one place: clients, jobs,
circuits, test readings and defects. it then produces a readable inspection report.

muriel field records & flags information. it doesn't certify anything.
reports are labelled as inspection records, not certificates of compliance. limit values are never built in: you enter one from the applicable standard, with its source.

**stack:** flask + jinja, sqlite, vanilla javascript (live reading check only).

# layout

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
| POST      | `/jobs/<id>/circuit` 🔒                 | add a circuit                                                |
| POST      | `/jobs/<id>/circuits/<cid>/edit` 🔒     | edit a circuit                                               |
| POST      | `/jobs/<id>/circuits/<cid>/delete` 🔒   | delete a circuit and its readings                            |
| POST      | `/jobs/<id>/circuits/<cid>/readings` 🔒 | record a reading; the server decides pass, flag or unchecked |
| POST      | `/jobs/<id>/circuits/<rid>/delete` 🔒   | delete a reading (typo correction)                           |
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