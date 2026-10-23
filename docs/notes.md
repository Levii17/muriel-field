# muriel field: notes & decisions

last updated: 2026-10-22
column and table below match `schema.sql`.
decisions made in review are logged under **decision log**; anything still undecided is under **open items** at the end.

## project basics

- **stack:** flask + jinja, sqlite, vanilla javascript for small interactions (e.g. live reading checks).
- **users:** one role (an electrician or small contractor managing their own jobs). no team features.
- **scope tiers:** good = accounts, clients jobs, circuits. better = readings with pass/flag, defects, forward-only job status, report page. best (only if time allows) = materials and costs, pdf export, link to a muriel schematics drawing.
- **non-goals:** offline mode or syncing, multiple roles, multi-company support, photo uploads, digital signatures, payments mobile apps, and account (user) deletion.'
- **safety:** the app records and flags information. it doesn't certify anything. reports are labelled as inspection records, not certificates of compliance.
- **limit values:** never invented. each `test_limit` row must carry its `source` (standard, edition, cluase or table) and starts with `verified = 0`. set `verified = 1` only after checking against the applicable standard. no limit values are seeded in `schema.sql`.

## database decisions
* **ownership model:** `clients` and `jobs` carry `user_id`. circuits and readings are reached only by joining through a job. defects belongs to a job.
* **database-level cross-user protection:** `clients` has `UNIQUE (id, user_id)`, and `jobs` has a composite `FOREIGN KEY (client_id, user_id) REFERENCES clients (id, user_id)`. likewise `circuits` has `UNIQUE (id, job_id)`, and a defect's `(circuit_id, job_id)` must match a circuit of the same job. this is a backstop to the route checks, not a replacement for them.
* **job status order:** `draft` → `in_progress` → `tested` → `reported`. a trigger (`jobs_status_forward_only`) rejects skips and backwards moves.
* **readings snapshot the limit:** `limit_id` records which `test_limits` row was used. `limit_comparison`, `limit_value` and `limit_verified` copy the rules as it was at save time. `limit_id` is `ON DELETE SET NULL`, so removing or editing a limit never changes an old reading (the lock trigger on `readings` has one narrow exception so this works for reported jobs, see the lock bullet below).
* **reading results:** `result` is `pass`, `flag` or `unchecked` (no matching limit). the word is `flag`, not `fail`, because the app doen't certify. a CHECK requires a checked reading to carry its full limit snapshot, including `limit_verified` (never NULL), Aand an unchecked reading to carry none of it. a second CHECK requires the stored `result` to agree with `value` against `limit_value` in the `limit_comaprison` direction. a reading on the limit passes. this catches a bug in the flask calculation before it reaches a report.
* **`test_types` lookup: small table holding each measurement's code, unit and direction (`max` = reading must be at or below the limit, `min` = at or above). both `test_limits` and `readings` reference it. it's seed data: the app never edits it, because readings snapshot the limit & comaprison but not the unit or label, so changing a unit would change the meaning of old readings. new test types can be added.