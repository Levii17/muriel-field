import re
import sqlite3
import pytest

from muriel import create_app
from muriel.db import init_db

class Browser:
    """ a test client that remembers its session and attached the CSRF token. """

    def __init__(self, app):
        self.c = app.test_client()

    def _token(self):
        with self.c.session_transaction() as s:
            s.setdefault("csrf_token", "test-token")
            return s["csrf_token"]

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **data):
        data.setdefault("csrf_token", self._token())
        return self.c.post(url, data=data)

    def register(self, name, email, password="correct horse"):
        return self.post("/register", name=name, email=email, password=password, confirm=password)

    def id_form(self, response, pattern):
        """ first capture group of `pattern` is a redirect location, as int. """
        return int(re.search(pattern, response.headers["Location"]).group(1))
    
@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": str(tmp_path / "t.sqlite")})
    with app.app_context():
        init_db()
    return app

@pytest.fixture
def raw(app):
    """ direct database access for assertions and for adding test limits. """
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()

@pytest.fixture
def luu(app):
    b = Browser(app)
    assert b.register("luu", "luu@example.com").status_code == 302
    return b

@pytest.fixture
def khanzy(app):
    b = Browser(app)
    assert b.register("khanzy", "khanzy@example.com").status_code == 302
    return b

@pytest.fixture
def job(luu):
    """ luu's client, a draft job, and one circuit (MCB B, 20, A). """
    luu.post("/clients/", name="Ona", phone="076 555 0100", email="onalenna@example.com")
    r = luu.post("/jobs/new", title="Kitchen DB", client_id="1", site_address="1 Test Street")
    job_id = luu.id_form(r, r"/jobs/(\d+)")
    luu.post(f"/jobs/{job_id}/circuits", name="Sockets", protection_type="MCB B", protection_rating_a="20")
    return job_id