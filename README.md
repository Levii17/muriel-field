# muriel Field

a small web app for electricians. it keeps job records in one place: clients, jobs,
circuits, test readings and defects. it then produces a readable inspection report.

muriel field records & flags information. it doesn't certify anything.
reports are labelled as inspection records, not certificates of compliance. limit values are never built in: you enter one from the applicable standard, with its source.

**stack:** flask + jinja, sqlite, vanilla javascript (live reading check only).

## routes

all routes except register & login require a logged-in user. every route below that takes a job id, looks the job up by id **&&** the logged-in user, so another user's job is a 404.
circuits, readings & defects are then looked up through that job.
routes marked 🔒 also call `refuse_if_locked(job)` and do nothing on a finalized job.

| method    | path                 | what it does                                        |
| --------- | -------------------- | --------------------------------------------------- |
| GET, POST | `/register`          | create an account (password hashed) and log in      |
| GET, POST | `/login`             | log in                                              |
| POST      | `/logout`            | clear the session                                   |
| GET       | `/`                  | dashboard: my jobs, status, open defect count       |
| GET, POST | `/clients/`          | list clients; add a client                          |
| GET, POST | `/clients/<id>/edit` | edit a client (finalized jobs keeps their snapshot) |
| GET, POST | `/jobs/new`          | create a job: the chosen client must belong to me   |
| GET       | `/jobs/<id>`         | job page: circuits, readings, defects               |
