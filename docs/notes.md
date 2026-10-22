# muriel field: notes & decisions

last updated: 2026-10-22
column and table below match 'schema.sql'.
decisions made in review are logged under **decision log**; anything still undecided is under **open items** at the end.

## project basics

* **stack:** flask + jinja, sqlite, vanilla javascript for small interactions (e.g. live reading checks).
* **users:** one role (an electrician or small contractor managing their own jobs). no team features.
* **scope tiers:** good = accounts, clients jobs, circuits. better = readings with pass/flag, defects, forward-only job status, report page. best (only if time allows) = materials and costs, pdf export, link to a muriel schematics drawing.
* **non-goals:** offline mode or syncing, multiple roles, multi-company support, photo uploads, digital signatures, payments mobile apps, and account (user) deletion.'
* **safety:** the app records and flags information. it doesn't certify anything. reports are labelled as inspection records, not certificates of compliance.
* **limit values:** never invented. each 'test_limit' row must carry its 'source' (standard, edition, cluase or table) and starts with 'verified = 0'. set 'verified = 1' only after checking against the applicable standard. no limit values are seeded in 'schema.sql'.