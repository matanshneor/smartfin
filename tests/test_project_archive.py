""""פרויקט הסתיים" (מתן, 30.9 — סבב 6, פריט 3).

פרויקט שהסתיים יוצא מהרשימה הראשית, מטופס ההוספה ומההגדרות — ונשאר
זמין: חלק "פרויקטים שהסתיימו" בעמוד הפרויקטים, העמוד שלו, ועסקה ישנה בו
שנערכת נשארת בו.
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"
_P_ACTIVE = "aaaaaaaa-0000-0000-0000-000000000001"
_P_DONE   = "aaaaaaaa-0000-0000-0000-000000000002"


def _projects():
    base = {"family_id": _FAM, "owner_id": None, "track_expense": True, "track_income": False,
            "track_savings": False, "budget_target": None, "description": None, "icon": "🔨",
            "created_at": "2026-01-01"}
    return [{**base, "id": _P_ACTIVE, "name": "טיול", "archived": False},
            {**base, "id": _P_DONE, "name": "שיפוץ", "archived": True}]


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase(projects=_projects(), transactions=[])
    monkeypatch.setattr(db, "get_client", lambda: f)
    return f


def test_the_active_list_leaves_out_finished_projects(fake):
    assert [p["name"] for p in db.get_projects(_FAM, _ME)] == ["טיול"]


def test_finished_projects_have_their_own_list(fake):
    done = db.get_projects(_FAM, _ME, archived=True)
    assert [p["name"] for p in done] == ["שיפוץ"] and done[0]["archived"] is True


def test_the_form_list_can_include_them_marked(fake):
    """טופס ההוספה צריך אותם — לעסקה ישנה שנערכת. מסומנים, כדי שלא יוצעו לחדשה."""
    allp = db.get_projects(_FAM, _ME, archived=None)
    assert {(p["name"], p["archived"]) for p in allp} == {("טיול", False), ("שיפוץ", True)}


def test_marking_finished_and_back(fake):
    assert db.set_project_archived(_P_ACTIVE, _FAM, True)
    assert [p["name"] for p in db.get_projects(_FAM, _ME)] == []
    assert db.set_project_archived(_P_ACTIVE, _FAM, False)
    assert [p["name"] for p in db.get_projects(_FAM, _ME)] == ["טיול"]


def test_a_missing_project_is_not_marked(fake):
    assert not db.set_project_archived("aaaaaaaa-0000-0000-0000-00000000ffff", _FAM, True)


# ── המסלולים ─────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch, fake):
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "get_family", lambda *a, **k: {"id": _FAM})
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield c


def test_the_archive_route(client):
    res = client.put(f"/api/projects/{_P_ACTIVE}/archive", json={"archived": True})
    assert res.status_code == 200
    assert client.get("/api/projects").get_json() == []
    res = client.put(f"/api/projects/{_P_ACTIVE}/archive", json={"archived": "yes"})
    assert res.status_code == 422


def test_the_form_list_route_includes_finished_ones_marked(client):
    body = client.get("/api/projects?include_archived=1").get_json()
    assert {(p["name"], p["archived"]) for p in body} == {("טיול", False), ("שיפוץ", True)}


def test_the_projects_page_has_two_sections():
    """מתן (30.9): "פרויקטים פעילים" ו"פרויקטים שהסתיימו", כל אחד עם הרשימה
    שלו — ולא חלק סגור בתחתית."""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parent.parent / "frontend/templates/projects.html").read_text(encoding="utf-8")
    assert '<h2 class="chart-title" style="flex:1;">פרויקטים פעילים</h2>' in tpl
    assert '<h2 class="chart-title">פרויקטים שהסתיימו</h2>' in tpl
    assert "<details" not in tpl
    assert tpl.index('id="activeProjects"') < tpl.index('id="finishedProjects"')


def test_the_page_renders_both_lists(client):
    html = client.get("/projects").get_data(as_text=True)
    active = html[html.index('id="activeProjects"'):html.index('id="finishedProjects"')]
    finished = html[html.index('id="finishedProjects"'):]
    assert "טיול" in active and "שיפוץ" not in active
    assert "שיפוץ" in finished


def test_finished_projects_have_no_arrow_but_still_open(client):
    """מתן (30.9): בלי החץ הקטן, אבל עדיין קישור לעמוד הפרויקט."""
    html = client.get("/projects").get_data(as_text=True)
    active = html[html.index('id="activeProjects"'):html.index('id="finishedProjects"')]
    finished = html[html.index('id="finishedProjects"'):]
    finished = finished[:finished.index("</section>")]
    assert "project-chevron" in active
    assert "project-chevron" not in finished
    assert f'href="/projects/{_P_DONE}"' in finished
