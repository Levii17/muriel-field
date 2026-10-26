"""
accounts: register, log in, log out, and the login_required decorator.
"""
import functools
import sqlite3

from flask import (Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db


