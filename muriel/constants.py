""" fixed lists shared by routes and templates. Edit to taste."""

# job stages, in order. the advance route walks this list; the database trigger
# jobs_status_forward_only enforces the same order.
STATUS_ORDER = ["draft", "in_progress", "tested", "reported"]
STATUS_LABELS = {
    "draft": "Draft",
    "in_progress": "In progress",
    "tested": "Tested",
    "reported": "Reported (final)",
}

# offered as a dropdown so limit matching never depends on free-text spelling.
# limit rows (flask add-limit) use the same names.
PROTECTION_TYPES = ["MCB B", "MCB C", "MCB D", "RCBO B", "RCBO C", "RCBO D", "Fuse", "Other"]

SEVERITIES = ["low", "medium", "high"]

def next_status(current):
    """ the stage after `current`, or None if `current` is the last one. """
    i = STATUS_ORDER.index(current)
    return STATUS_ORDER[i + 1] if i + 1 < len(STATUS_ORDER) else None

def canonical_protection_type(raw):
    """ return the dropdown spelling for `raw` (case-insensitive), or None."""
    wanted = (raw or "").strip().lower()
    for name in PROTECTION_TYPES:
        if name.lower() == wanted:
            return name
    return None