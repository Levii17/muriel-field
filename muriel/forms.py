""" tiny helpers for reading form fields. """
from flask import request

def field(name, max_len=200):
    """ stripped text, truncated; empty string if absent. """
    return (request.form.get(name) or "").strip()[:max_len]

def optional(name, max_len=200):
    """ like field(), but None when empty (stored as NULL). """
    return field(name, max_len) or None

def int_field(name):
    """ an int, or None if absent or not a whole number. """
    try:
        return int((request.form.get(name) or "").strip())
    except ValueError:
        return None