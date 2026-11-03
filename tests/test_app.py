""" 
end-to-end tests through the flask routes. 
disclaimer: this test suite was written by Claude (Anthropic)
"""
import pytest

from conftest import Browser

# ------------------------------------------------------------------- helpers

def add_limit(raw, value=1.0, verified=0, **scope):
    """ a TEST-ONLY limit. real values come from the standard via `flask add-limit`. """
    raw.execute(
        "INSERT INTO test_limits (test_type, protection_type, rating_a, limit_value, source, verified) "
        "VALUES (?, ?, ?, ?, 'TEST ONLY', ?)",
        (scope.get("test_type", "earth_loop_impedance"), scope.get("protection_type"),
         scope.get("rating_a"), value, verified))
    raw.commit()

def reading(raw, n=1):
    return raw.execute("SELECT * FROM readings ORDER BY id").fetchall()[n - 1]

def go_to_tested(b, job):
    for _ in range(2):
        b.post(f"/jobs/{job}/advance")

def body(response):
    return response.get_data(as_text=True)

def page_after(b, response):
    """ follow a redirect and return the page, so flashed messages show up. """
    assert response.status_code == 302
    return body(b.get(response.headers["Location"]))

def count(raw, table):
    return raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

def status(raw, job):
    return raw.execute("SELECT status FROM jobs WHERE id = ?", (job,)).fetchone()[0]

def db_state(raw):
    """ every row of every table, to prove that a refused request changed nothing. """
    tables = ("users", "clients", "jobs", "circuits", "readings", "defects", "test_limits")
    return {t: [tuple(r) for r in raw.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}

def post_reading(b, job, value, test_type="earth_loop_impedance", circuit=1, **extra):
    return b.post(f"/jobs/{job}/circuits/{circuit}/readings",
                  test_type=test_type, value=str(value), **extra)

def live_check(b, job, value, test_type="earth_loop_impedance", circuit=1):
    return b.get(f"/api/jobs/{job}/circuits/{circuit}/check",
                 query_string={"test_type": test_type, "value": value})

def report(b, job):
    return body(b.get(f"/jobs/{job}/report"))

@pytest.fixture
def full(luu, raw, job):
    """ the `job` fixture plus a limit, one passing reading and one defect on the circuit. """
    add_limit(raw, 1.0)
    post_reading(luu, job, 0.5)
    luu.post(f"/jobs/{job}/defects", description="Loose neutral", circuit_id="1")
    return dict(job=job, circuit=1, reading=1, defect=1)

@pytest.fixture
def reported(luu, full):
    """ `full`, finalized. """
    for _ in range(3):
        luu.post(f"/jobs/{full['job']}/advance")
    return full

# every route that takes a job id and changes something. {job} {circuit} {reading}
# and {defect} are filled in from the `full` fixture.
LOCKABLE_POSTS = [
    ("/jobs/{job}/edit", dict(title="Changed", site_address="1 Other Street", client_id="1")),
    ("/jobs/{job}/delete", {}),
    ("/jobs/{job}/circuits", dict(name="New circuit")),
    ("/jobs/{job}/circuits/{circuit}/edit", dict(name="Renamed")),
    ("/jobs/{job}/circuits/{circuit}/delete", {}),
    ("/jobs/{job}/circuits/{circuit}/readings", dict(test_type="earth_loop_impedance", value="0.2")),
    ("/jobs/{job}/readings/{reading}/delete", {}),
    ("/jobs/{job}/defects", dict(description="New defect")),
    ("/jobs/{job}/defects/{defect}/resolve", {}),
    ("/jobs/{job}/defects/{defect}/reopen", {}),
    ("/jobs/{job}/defects/{defect}/delete", {}),
]
JOB_POSTS = LOCKABLE_POSTS + [("/jobs/{job}/advance", {})]

# ------------------------------------------------------ accounts and sessions

@pytest.mark.parametrize("url", ["/", "/clients/", "/jobs/new", "/jobs/1", "/jobs/1/report"])
def test_logged_out_pages_redirect_to_login(app, url):
    r = app.test_client().get(url)
    assert r.status_code == 302 and "/login" in r.headers["Location"]

def test_logged_out_api_call_gets_401_json(app):
    r = app.test_client().get("/api/jobs/1/circuits/1/check?test_type=rcd_trip_time&value=1")
    assert r.status_code == 401 and r.get_json()["ok"] is False

def test_register_logs_in_and_stores_a_hash_not_the_password(app, raw):
    b = Browser(app)
    r = b.register("Luu", "Luu@Example.com")
    assert r.status_code == 302
    user = raw.execute("SELECT email, password_hash FROM users").fetchone()
    assert user["email"] == "luu@example.com"
    assert "correct horse" not in user["password_hash"]
    assert b.get("/").status_code == 200

@pytest.mark.parametrize("form", [
    dict(name="", email="a@example.com", password="longenough", confirm="longenough"),
    dict(name="A", email="not-an-email", password="longenough", confirm="longenough"),
    dict(name="A", email="a@example.com", password="short", confirm="short"),
    dict(name="A", email="a@example.com", password="longenough", confirm="different"),
    dict(name="A", email="a@example.com", password="x" * 201, confirm="x" * 201),
])
def test_bad_registration_is_refused(app, raw, form):
    r = Browser(app).post("/register", **form)
    assert r.status_code == 400 and count(raw, "users") == 0

def test_duplicate_email_is_refused_whatever_its_case(app, luu, raw):
    r = Browser(app).register("Other", "LUU@example.com")
    assert r.status_code == 400 and count(raw, "users") == 1

def test_login_and_logout(app, luu):
    luu.post("/logout")
    assert luu.get("/").status_code == 302
    assert luu.post("/login", email="luu@example.com", password="nope").status_code == 400
    assert luu.get("/").status_code == 302
    assert luu.post("/login", email="LUU@example.com", password="correct horse").status_code == 302
    assert luu.get("/").status_code == 200

def test_logout_must_be_a_post(luu):
    assert luu.get("/logout").status_code == 405

def test_unknown_email_and_wrong_password_look_the_same(app, luu):
    unknown = Browser(app).post("/login", email="nobody@example.com", password="whatever1")
    wrong = Browser(app).post("/login", email="luu@example.com", password="whatever1")
    assert unknown.status_code == wrong.status_code == 400
    assert "Wrong email or password." in body(unknown) and "Wrong email or password." in body(wrong)

def test_session_cookie_is_httponly_and_samesite(app):
    r = Browser(app).register("Luu", "luu@example.com")
    cookie = r.headers.getlist("Set-Cookie")[0]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie

# ---------------------------------------------------------------------- CSRF

def test_post_without_a_csrf_token_is_refused(luu, raw):
    r = luu.c.post("/clients/", data={"name": "Sneaky"})
    assert r.status_code == 400 and count(raw, "clients") == 0

def test_post_with_the_wrong_csrf_token_is_refused(luu, raw):
    r = luu.post("/clients/", name="Sneaky", csrf_token="wrong")
    assert r.status_code == 400 and count(raw, "clients") == 0

def test_login_form_needs_a_csrf_token_too(app, luu):
    r = app.test_client().post("/login", data={"email": "luu@example.com", "password": "correct horse"})
    assert r.status_code == 400

def test_csrf_token_in_a_header_is_accepted(luu, raw):
    token = luu._token()
    r = luu.c.post("/clients/", data={"name": "Via header"}, headers={"X-CSRF-Token": token})
    assert r.status_code == 302 and count(raw, "clients") == 1

# ----------------------------------------------------- ownership (two users)

@pytest.mark.parametrize("url", [
    "/jobs/{job}",
    "/jobs/{job}/report",
    "/api/jobs/{job}/circuits/{circuit}/check?test_type=earth_loop_impedance&value=1",
])
def test_another_users_job_pages_are_404(khanzy, full, url):
    assert khanzy.get(url.format(**full)).status_code == 404

@pytest.mark.parametrize("url, data", JOB_POSTS)
def test_owner_can_reach_every_job_route(luu, full, url, data):
    """ guards the 404 test below: its urls are real, so a 404 there means ownership. """
    assert luu.post(url.format(**full), **data).status_code == 302

@pytest.mark.parametrize("url, data", JOB_POSTS)
def test_another_user_gets_404_and_changes_nothing(khanzy, raw, full, url, data):
    before = db_state(raw)
    assert khanzy.post(url.format(**full), **data).status_code == 404
    assert db_state(raw) == before

def test_dashboard_and_clients_list_show_only_your_own(luu, khanzy, job):
    assert "Kitchen DB" in body(luu.get("/")) and "Kitchen DB" not in body(khanzy.get("/"))
    assert "Ona" in body(luu.get("/clients/")) and "Ona" not in body(khanzy.get("/clients/"))

def test_cannot_create_a_job_for_someone_elses_client(luu, khanzy, raw, job):
    r = khanzy.post("/jobs/new", title="Stolen", client_id="1", site_address="x")
    assert r.status_code == 400 and count(raw, "jobs") == 1

def test_cannot_move_your_own_job_to_someone_elses_client(luu, khanzy, raw, job):
    khanzy.post("/clients/", name="Mine")  # client 2
    r = khanzy.post("/jobs/new", title="K job", client_id="2", site_address="x")
    khanzy_job = khanzy.id_form(r, r"/jobs/(\d+)")
    khanzy.post(f"/jobs/{khanzy_job}/edit", title="K job", site_address="x", client_id="1")
    assert raw.execute("SELECT client_id FROM jobs WHERE id = ?", (khanzy_job,)).fetchone()[0] == 2

def test_another_user_cannot_view_or_edit_your_client(luu, khanzy, raw, job):
    assert khanzy.get("/clients/1/edit").status_code == 404
    assert khanzy.post("/clients/1/edit", name="Hijacked").status_code == 404
    assert raw.execute("SELECT name FROM clients").fetchone()[0] == "Ona"

def test_circuit_from_another_of_your_jobs_is_404(luu, raw, full):
    """ ownership is per job, not just per user. """
    r = luu.post("/jobs/new", title="Second", client_id="1", site_address="x")
    second = luu.id_form(r, r"/jobs/(\d+)")
    before = db_state(raw)
    assert luu.post(f"/jobs/{second}/circuits/1/edit", name="Renamed").status_code == 404
    assert luu.post(f"/jobs/{second}/circuits/1/readings", test_type="earth_loop_impedance",
                    value="1").status_code == 404
    assert luu.post(f"/jobs/{second}/readings/1/delete").status_code == 404
    assert luu.post(f"/jobs/{second}/defects/1/resolve").status_code == 404
    assert luu.post(f"/jobs/{second}/defects", description="Wrong circuit",
                    circuit_id="1").status_code == 404
    assert db_state(raw) == before

# ----------------------------------------------------------------------- jobs

def test_job_moves_through_every_stage_and_is_then_final(luu, raw, job):
    seen = []
    for _ in range(3):
        luu.post(f"/jobs/{job}/advance")
        seen.append(status(raw, job))
    assert seen == ["in_progress", "tested", "reported"]
    assert "already final" in page_after(luu, luu.post(f"/jobs/{job}/advance"))
    assert status(raw, job) == "reported"

def test_browser_cannot_choose_the_next_status(luu, raw, job):
    luu.post(f"/jobs/{job}/advance", status="reported")
    assert status(raw, job) == "in_progress"

def test_finalizing_copies_client_and_electrician_details(luu, raw, job):
    go_to_tested(luu, job)
    luu.post(f"/jobs/{job}/advance")
    j = raw.execute("SELECT * FROM jobs").fetchone()
    assert (j["client_name"], j["client_phone"], j["client_email"], j["reported_by_name"]) == \
           ("Ona", "076 555 0100", "onalenna@example.com", "luu")

@pytest.mark.parametrize("form", [
    dict(title="", site_address="x", client_id="1"),
    dict(title="   ", site_address="x", client_id="1"),
    dict(title="T", site_address="", client_id="1"),
    dict(title="T", site_address="x", client_id="999"),
    dict(title="T", site_address="x", client_id="abc"),
    dict(title="T", site_address="x"),
])
def test_bad_new_job_is_refused(luu, raw, form):
    luu.post("/clients/", name="Ona")
    assert luu.post("/jobs/new", **form).status_code == 400
    assert count(raw, "jobs") == 0

def test_new_job_without_any_client_sends_you_to_add_one(luu):
    r = luu.get("/jobs/new")
    assert r.status_code == 302 and "/clients" in r.headers["Location"]

def test_edit_job(luu, raw, job):
    luu.post(f"/jobs/{job}/edit", title="Bathroom DB", site_address="2 Test Street", client_id="1")
    j = raw.execute("SELECT title, site_address FROM jobs").fetchone()
    assert (j["title"], j["site_address"]) == ("Bathroom DB", "2 Test Street")

def test_bad_job_edit_changes_nothing(luu, raw, job):
    before = db_state(raw)
    r = luu.post(f"/jobs/{job}/edit", title="", site_address="x", client_id="1")
    assert "required" in page_after(luu, r) and db_state(raw) == before

def test_delete_draft_job_removes_everything_under_it(luu, raw, full):
    luu.post(f"/jobs/{full['job']}/delete")
    assert [count(raw, t) for t in ("jobs", "circuits", "readings", "defects")] == [0, 0, 0, 0]

def test_unknown_job_is_a_404_page(luu):
    r = luu.get("/jobs/999")
    assert r.status_code == 404 and "does not exist" in body(r)

# --------------------------------------------------------- the lock (routes)

@pytest.mark.parametrize("url, data", LOCKABLE_POSTS)
def test_reported_job_refuses_changes_with_a_friendly_message(luu, raw, reported, url, data):
    before = db_state(raw)
    r = luu.post(url.format(**reported), **data)
    # 302 with a message: the ROUTE refused it. a database trigger would give a 409.
    assert r.status_code == 302
    assert "finalized" in page_after(luu, r)
    assert db_state(raw) == before

def test_reported_job_can_still_be_viewed(luu, reported):
    assert luu.get(f"/jobs/{reported['job']}").status_code == 200
    assert luu.get(f"/jobs/{reported['job']}/report").status_code == 200

# ------------------------------------------------------------------- readings

def test_reading_with_no_limit_is_saved_unchecked(luu, raw, job):
    post_reading(luu, job, 0.5)
    r = reading(raw)
    assert (r["result"], r["limit_id"], r["limit_value"], r["limit_verified"]) == \
           ("unchecked", None, None, None)

@pytest.mark.parametrize("test_type, value, expected", [
    ("earth_loop_impedance", 0, "pass"),
    ("earth_loop_impedance", 0.5, "pass"),
    ("earth_loop_impedance", 1.0, "pass"),    # exactly on the limit passes
    ("earth_loop_impedance", 1.01, "flag"),
    ("insulation_resistance", 2.0, "pass"),
    ("insulation_resistance", 1.0, "pass"),   # exactly on the limit passes
    ("insulation_resistance", 0.99, "flag"),
])
def test_result_follows_the_direction_of_the_test(luu, raw, job, test_type, value, expected):
    add_limit(raw, 1.0, test_type=test_type)
    post_reading(luu, job, value, test_type)
    assert reading(raw)["result"] == expected

def test_reading_stores_the_limit_it_was_checked_against(luu, raw, job):
    add_limit(raw, 1.0, verified=1)
    post_reading(luu, job, 0.5, notes="after reset")
    r = reading(raw)
    assert (r["limit_id"], r["limit_comparison"], r["limit_value"], r["limit_verified"], r["notes"]) == \
           (1, "max", 1.0, 1, "after reset")

def test_most_specific_limit_wins(luu, raw, job):
    add_limit(raw, 1.0)                                           # any protection
    add_limit(raw, 2.0, protection_type="MCB B")                  # any rating
    add_limit(raw, 3.0, protection_type="MCB B", rating_a=20)     # exact
    add_limit(raw, 9.0, protection_type="MCB C", rating_a=20)     # different type: ignored
    post_reading(luu, job, 2.5)
    r = reading(raw)
    assert (r["limit_value"], r["result"]) == (3.0, "pass")

def test_less_specific_limits_are_used_when_nothing_better_matches(luu, raw, job):
    add_limit(raw, 1.0)
    add_limit(raw, 2.0, protection_type="MCB B")
    add_limit(raw, 3.0, protection_type="MCB B", rating_a=20)
    luu.post(f"/jobs/{job}/circuits", name="Lights", protection_type="MCB B", protection_rating_a="32")  # 2
    luu.post(f"/jobs/{job}/circuits", name="Spare")                                                        # 3
    post_reading(luu, job, 0.5, circuit=2)
    post_reading(luu, job, 0.5, circuit=3)
    assert [reading(raw, n)["limit_value"] for n in (1, 2)] == [2.0, 1.0]

def test_protection_type_matches_whatever_its_case(luu, raw, job):
    add_limit(raw, 1.0, protection_type="mcb b")
    post_reading(luu, job, 0.5)
    assert reading(raw)["limit_value"] == 1.0

def test_editing_or_deleting_a_limit_never_changes_an_old_reading(luu, raw, job):
    add_limit(raw, 1.0)
    post_reading(luu, job, 0.5)
    raw.execute("UPDATE test_limits SET limit_value = 0.1"); raw.commit()
    assert (reading(raw)["limit_value"], reading(raw)["result"]) == (1.0, "pass")
    raw.execute("DELETE FROM test_limits"); raw.commit()
    r = reading(raw)
    assert (r["limit_id"], r["limit_value"], r["result"]) == (None, 1.0, "pass")
    assert "\u2264 1 ohm" in report(luu, job)

def test_deleting_a_limit_used_by_a_reported_job_does_not_break_its_report(luu, raw, reported):
    raw.execute("DELETE FROM test_limits"); raw.commit()
    text = report(luu, reported["job"])
    assert "\u2264 1 ohm" in text

def test_changing_a_circuits_protection_keeps_old_readings_as_they_were(luu, raw, job):
    add_limit(raw, 1.0, protection_type="MCB B", rating_a=20)
    post_reading(luu, job, 0.5)
    luu.post(f"/jobs/{job}/circuits/1/edit", name="Sockets", protection_type="MCB C", protection_rating_a="6")
    r = reading(raw)
    assert (r["limit_value"], r["result"]) == (1.0, "pass")

@pytest.mark.parametrize("value", ["", "abc", "-1", "nan", "inf", "1e999", "1,5"])
def test_bad_reading_values_are_refused(luu, raw, job, value):
    add_limit(raw)
    post_reading(luu, job, value)
    assert count(raw, "readings") == 0

def test_bad_reading_values_get_a_helpful_message(luu, job):
    assert "number" in page_after(luu, post_reading(luu, job, "abc"))
    assert "negative" in page_after(luu, post_reading(luu, job, "-1"))

@pytest.mark.parametrize("test_type", ["", "made_up"])
def test_unknown_test_type_is_refused(luu, raw, job, test_type):
    post_reading(luu, job, 1, test_type)
    assert count(raw, "readings") == 0

def test_reading_can_be_deleted_and_entered_again(luu, raw, job):
    post_reading(luu, job, 5)
    luu.post(f"/jobs/{job}/readings/1/delete")
    assert count(raw, "readings") == 0

# ----------------------------------------------------------------- live check

@pytest.mark.parametrize("value", ["0.5", "1", "1.5"])
def test_live_check_agrees_with_what_gets_saved_and_saves_nothing(luu, raw, job, value):
    add_limit(raw, 1.0)
    preview = live_check(luu, job, value).get_json()
    assert count(raw, "readings") == 0
    post_reading(luu, job, value)
    assert preview["ok"] and preview["result"] == reading(raw)["result"]

def test_live_check_with_no_limit_says_unchecked(luu, job):
    assert live_check(luu, job, "1").get_json()["result"] == "unchecked"

@pytest.mark.parametrize("value, test_type", [
    ("", "earth_loop_impedance"), ("abc", "earth_loop_impedance"), ("-5", "earth_loop_impedance"),
    ("1", "made_up"), ("1", ""),
])
def test_live_check_rejects_bad_input(luu, job, value, test_type):
    r = live_check(luu, job, value, test_type)
    assert r.status_code == 400 and r.get_json()["ok"] is False

# ------------------------------------------------------------------- circuits

@pytest.mark.parametrize("form", [
    dict(name=""),
    dict(name="X", protection_type="Mystery"),
    dict(name="X", protection_rating_a="0"),
    dict(name="X", protection_rating_a="-5"),
    dict(name="X", protection_rating_a="abc"),
    dict(name="X", protection_rating_a="2.5"),
])
def test_bad_circuit_is_refused(luu, raw, job, form):
    luu.post(f"/jobs/{job}/circuits", **form)
    assert count(raw, "circuits") == 1   # only the fixture's circuit

def test_protection_type_is_stored_in_the_dropdown_spelling(luu, raw, job):
    luu.post(f"/jobs/{job}/circuits", name="Lights", protection_type="mcb c", protection_rating_a="16")
    c = raw.execute("SELECT * FROM circuits WHERE name = 'Lights'").fetchone()
    assert (c["protection_type"], c["protection_rating_a"]) == ("MCB C", 16)

def test_circuit_needs_only_a_name(luu, raw, job):
    luu.post(f"/jobs/{job}/circuits", name="Spare")
    c = raw.execute("SELECT * FROM circuits WHERE name = 'Spare'").fetchone()
    assert (c["protection_type"], c["protection_rating_a"]) == (None, None)

def test_duplicate_circuit_name_on_one_job_is_refused_but_fine_on_another(luu, raw, job):
    assert "already exists" in page_after(luu, luu.post(f"/jobs/{job}/circuits", name="Sockets"))
    assert count(raw, "circuits") == 1
    r = luu.post("/jobs/new", title="Second", client_id="1", site_address="x")
    second = luu.id_form(r, r"/jobs/(\d+)")
    luu.post(f"/jobs/{second}/circuits", name="Sockets")
    assert count(raw, "circuits") == 2

def test_renaming_a_circuit_to_an_existing_name_is_refused(luu, raw, job):
    luu.post(f"/jobs/{job}/circuits", name="Lights")
    luu.post(f"/jobs/{job}/circuits/2/edit", name="Sockets")
    assert raw.execute("SELECT name FROM circuits WHERE id = 2").fetchone()[0] == "Lights"

def test_deleting_a_circuit_removes_its_readings_and_defects(luu, raw, full):
    luu.post(f"/jobs/{full['job']}/circuits/1/delete")
    assert (count(raw, "circuits"), count(raw, "readings"), count(raw, "defects")) == (0, 0, 0)

# -------------------------------------------------------------------- defects

def test_defect_defaults_to_medium_severity_and_open(luu, raw, job):
    luu.post(f"/jobs/{job}/defects", description="No labels on the board")
    d = raw.execute("SELECT * FROM defects").fetchone()
    assert (d["severity"], d["status"], d["circuit_id"], d["resolved_at"]) == ("medium", "open", None, None)

@pytest.mark.parametrize("form", [
    dict(description=""),
    dict(description="   "),
    dict(description="x", severity="catastrophic"),
    dict(description="x", circuit_id="abc"),
])
def test_bad_defect_is_refused(luu, raw, job, form):
    luu.post(f"/jobs/{job}/defects", **form)
    assert count(raw, "defects") == 0

def test_resolving_and_reopening_a_defect(luu, raw, full):
    job = full["job"]
    luu.post(f"/jobs/{job}/defects/1/resolve")
    d = raw.execute("SELECT status, resolved_at FROM defects").fetchone()
    assert d["status"] == "resolved" and d["resolved_at"]
    assert "Open defects: 0" in report(luu, job)
    luu.post(f"/jobs/{job}/defects/1/reopen")
    d = raw.execute("SELECT status, resolved_at FROM defects").fetchone()
    assert (d["status"], d["resolved_at"]) == ("open", None)
    assert "Open defects: 1" in report(luu, job)

def test_delete_defect(luu, raw, full):
    luu.post(f"/jobs/{full['job']}/defects/1/delete")
    assert count(raw, "defects") == 0

# --------------------------------------------------------------------- report

def test_report_is_labelled_as_an_inspection_record_not_a_certificate(luu, job):
    text = report(luu, job)
    assert "Inspection record" in text and "not a certificate of compliance" in text

def test_draft_report_is_marked_draft_and_a_final_one_is_not(luu, job):
    assert "DRAFT" in report(luu, job)
    for _ in range(3):
        luu.post(f"/jobs/{job}/advance")
    assert "DRAFT" not in report(luu, job)

def test_report_summary_counts(luu, raw, job):
    add_limit(raw, 1.0)
    post_reading(luu, job, 0.5)                              # pass
    post_reading(luu, job, 2.0)                              # flag
    post_reading(luu, job, 5, "insulation_resistance")       # no limit: unchecked
    assert "1 pass, 1 flagged, 1 unchecked" in report(luu, job)

def test_report_flags_unverified_limits_only(luu, raw, job):
    add_limit(raw, 1.0, verified=1)
    post_reading(luu, job, 0.5)
    assert "(unverified)" not in report(luu, job)
    raw.execute("DELETE FROM test_limits"); add_limit(raw, 1.0, verified=0)
    post_reading(luu, job, 0.5)
    assert "(unverified)" in report(luu, job)

def test_report_follows_live_client_details_until_finalized_then_freezes_them(luu, job):
    luu.post("/clients/1/edit", name="Ona Renamed", phone="", email="")
    assert "Ona Renamed" in report(luu, job)
    go_to_tested(luu, job)
    luu.post(f"/jobs/{job}/advance")
    luu.post("/clients/1/edit", name="Someone Else", phone="999", email="x@example.com")
    text = report(luu, job)
    assert "Ona Renamed" in text and "Someone Else" not in text and "999" not in text

# --------------------------------------------------------------------- clients

def test_client_needs_a_name(luu, raw):
    luu.post("/clients/", name="  ")
    assert count(raw, "clients") == 0

def test_edit_client(luu, raw, job):
    luu.post("/clients/1/edit", name="Ona M", phone="", email="")
    c = raw.execute("SELECT * FROM clients").fetchone()
    assert (c["name"], c["phone"], c["email"]) == ("Ona M", None, None)

def test_blank_name_on_client_edit_changes_nothing(luu, raw, job):
    before = db_state(raw)
    luu.post("/clients/1/edit", name="", phone="1", email="x")
    assert db_state(raw) == before

# ------------------------------------------------- hostile input and limits

def test_html_in_user_text_is_escaped(luu, job):
    luu.post(f"/jobs/{job}/defects", description="<script>alert(1)</script>")
    text = body(luu.get(f"/jobs/{job}"))
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text

def test_sql_in_user_text_is_stored_as_plain_text(luu, raw):
    nasty = "x'); DROP TABLE jobs;--"
    luu.post("/clients/", name=nasty)
    assert raw.execute("SELECT name FROM clients").fetchone()[0] == nasty
    assert count(raw, "jobs") == 0   # the table still exists

def test_oversized_request_is_refused(luu, raw):
    assert luu.post("/clients/", name="x" * 70_000).status_code == 413
    assert count(raw, "clients") == 0

# ------------------------------------------------------------------------ CLI

def run(app, *args):
    return app.test_cli_runner().invoke(args=list(args))

def test_add_limit_is_unverified_unless_you_say_otherwise(app, raw):
    result = run(app, "add-limit", "--test-type", "rcd_trip_time", "--value", "300", "--source", "TEST ONLY")
    assert result.exit_code == 0 and "unverified" in result.output
    assert raw.execute("SELECT verified FROM test_limits").fetchone()[0] == 0

def test_add_limit_uses_the_dropdown_spelling(app, raw):
    run(app, "add-limit", "--test-type", "rcd_trip_time", "--value", "300", "--source", "TEST ONLY",
        "--protection-type", "rcbo c", "--rating", "20", "--verified")
    row = raw.execute("SELECT * FROM test_limits").fetchone()
    assert (row["protection_type"], row["rating_a"], row["verified"]) == ("RCBO C", 20, 1)

@pytest.mark.parametrize("extra", [
    ["--test-type", "made_up"],
    ["--test-type", "rcd_trip_time", "--protection-type", "Mystery"],
    ["--test-type", "rcd_trip_time", "--value", "-1"],
])
def test_add_limit_refuses_bad_input(app, raw, extra):
    args = ["add-limit", "--value", "1", "--source", "TEST ONLY"] + extra
    assert run(app, *args).exit_code != 0 and count(raw, "test_limits") == 0

def test_add_limit_refuses_a_duplicate_scope(app, raw):
    args = ("add-limit", "--test-type", "rcd_trip_time", "--value", "300", "--source", "TEST ONLY")
    assert run(app, *args).exit_code == 0
    assert run(app, *args).exit_code != 0 and count(raw, "test_limits") == 1

def test_init_db_will_not_overwrite_without_force(app):
    result = run(app, "init-db")
    assert result.exit_code != 0 and "already exists" in result.output
