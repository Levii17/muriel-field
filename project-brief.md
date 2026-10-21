# Muriel Field: Project Brief

*CS50 final project. Draft v1. Rewrite in your own words before submitting.*

## Problem

Electricians often record inspection details on paper: circuits, test readings, and defects found on site. Paper is easy to lose, hard to search, and slow to turn into a clean report. Muriel Field is a small web app that keeps those records in one place and produces a readable inspection report from them.

## Target user

A working electrician or small contractor managing their own jobs. One user role, no team features.

## Core use cases

1. Log in and see my jobs with their status and open defects.
2. Create a job for a client and site.
3. Record the job's circuits (name, description, protection rating).
4. Record test readings and see immediately whether each is within its limit.
5. Log defects, then mark them resolved or reopen them.
6. Move a job forward through its stages and view a printable report.

## Scope

**Good (must ship):** accounts, clients, jobs, circuits, with every query scoped to the logged-in user.

**Better (target):** test readings with pass or flag results from a limits table, defects with open and resolved states, job status that only moves forward, and a report page.

**Best (only if time allows):** materials and costs, PDF export, and a link to a Muriel Schematics drawing on a job.

## Non-goals

Offline mode or syncing, multiple user roles, multi-company support, photo uploads, digital signatures, payments, and mobile apps.

## Technical approach

Flask and Jinja for the backend and pages, SQLite for storage, and vanilla JavaScript for small interactions such as live reading checks. Main tables: users, clients, jobs, circuits, readings, defects, and test limits.

## Safety note

The app records and flags information. It does not certify anything, and reports are labelled as inspection records, not certificates of compliance. Limit values are stored in a table and must be taken from the applicable standard and checked, not invented.

## Success criteria

- A new user can register, create a job, add circuits, readings, and a defect, and view the report without errors.
- No user can view or edit another user's data.
- The demo video shows the whole flow.
- I can explain every route, table, and design choice in my README.
