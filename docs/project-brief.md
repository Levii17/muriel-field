# muriel field: project brief

_CS50 final project._

## problem

electricians often record inspection details on paper: circuits, test readings, and defects found on site. paper is easy to lose, hard to search, and slow to turn into a clean report. muriel Field is a small web app that keeps those records in one place and produces a readable inspection report from them.

## target user

a working electrician or small contractor managing their own jobs. one user role, no team features.

## core use cases

1. log in and see my jobs with their status and open defects.
2. create a job for a client and site.
3. record the job's circuits (name, description, protection rating).
4. record test readings and see immediately whether each is within its limit.
5. log defects, then mark them resolved or reopen them.
6. move a job forward through its stages and view a printable report.

## scope

**good (must ship):** accounts, clients, jobs, circuits, with every query scoped to the logged-in user.

**better (target):** test readings with pass or flag results from a limits table, defects with open and resolved states, job status that only moves forward, and a report page.

**best (only if time allows):** materials and costs, PDF export, and a link to a [muriel schematics](https://levii17.github.io/muriel-schematics/) drawing on a job

## non-goals

offline mode or syncing, multiple user roles, multi-company support, photo uploads, digital signatures, payments, and mobile apps.

## technical approach

flask and jinja for the backend and pages, sqlite for storage, and vanilla javascript for small interactions such as live reading checks. main tables: users, clients, jobs, circuits, readings, defects, and test limits.

## safety note

the app records and flags information. it does not certify anything, and reports are labelled as inspection records, not certificates of compliance. limit values are stored in a table and must be taken from the applicable standard and checked, not invented.

## success criteria

- a new user can register, create a job, add circuits, readings, and a defect, and view the report without errors.
- no user can view or edit another user's data.
- the demo video shows the whole flow.
- i can explain every route, table, and design choice in my README.
