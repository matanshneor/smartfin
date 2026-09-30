"""בדיקת דפדפן אמיתי: מאזן הפרויקט (הכנסות פחות הוצאות) בשורה נפרדת בראש עמוד הפרויקט.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/project_net.py
"""
import os, json, time, datetime, subprocess, signal, sys
from playwright.sync_api import sync_playwright

ROOT = os.getcwd()
def _dotenv(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    return out
env = {**os.environ, **{k: v for k, v in _dotenv(os.path.join(ROOT, ".env")).items() if v}}
env["PORT"] = "8099"
srv = subprocess.Popen([os.path.join(ROOT, ".venv/bin/python3"), "-m", "backend.app"], cwd=ROOT, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       start_new_session=True)   # במצב פיתוח Flask מוליד תהליך-בן שחייב למות איתו
BASE = "http://127.0.0.1:8099"


created = None
cat = None
try:
    for _ in range(40):
        try:
            import urllib.request; urllib.request.urlopen(BASE + "/health", timeout=1); break
        except Exception: time.sleep(0.5)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 390, "height": 844})
        page.goto(BASE + "/login")
        page.fill("#identifier", env.get("RLS_TEST_EMAIL_A", "rls-test-family-a@smartfin.test"))
        page.fill("#password", env["RLS_TEST_PASSWORD_A"])
        page.click("button.submit-btn")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        def api(method, url, body=None):
            r = page.request.fetch(BASE + url, method=method, data=json.dumps(body) if body else None,
                                   headers={"Content-Type": "application/json"})
            return r.status, (r.json() if r.body() else None)

        def project(name, income):
            st, proj = api("POST", "/api/projects", {"name": name, "track_expense": True,
                                                     "track_income": income, "track_savings": False})
            return (proj.get("project") or proj)["id"]

        def add(pid, kind, amount):
            cats = page.request.get(BASE + f"/api/projects/{pid}/categories?type={kind}").json()
            api("POST", "/api/transactions", {"amount": amount, "type": kind, "date": "2026-09-12",
                                              "description": "NET-TX", "project_id": pid,
                                              "project_category_id": cats[0]["id"]})

        def net(pid):
            page.goto(BASE + f"/projects/{pid}"); page.wait_for_timeout(700)
            if not page.locator(".project-net").count():
                return "no net row"
            return page.inner_text(".project-net-value") + " | " + page.get_attribute(".project-net", "class")

        both = project("NET-PROJ", True)
        add(both, "income", 1000.50); add(both, "expense", 300.25)
        print("income 1000.50, expense 300.25 →", net(both))
        page.locator(".hero-totals").scroll_into_view_if_needed()
        page.screenshot(path="/tmp/net.png", clip={"x": 0, "y": 0, "width": 390, "height": 330})
        add(both, "expense", 900)
        print("+ expense 900 →", net(both))
        only_exp = project("NET-PROJ", False)
        add(only_exp, "expense", 50)
        print("expense-only project →", net(only_exp))
        b.close()
finally:
    cleanup = "\n".join([
        "import os, sys", "sys.path.insert(0, '.')",
        "from dotenv import load_dotenv; load_dotenv('.env')",
        "from backend import supabase_config as db",
        "r, _ = db.sign_in(os.environ.get('RLS_TEST_EMAIL_A', 'rls-test-family-a@smartfin.test'), os.environ['RLS_TEST_PASSWORD_A'])",
        "db.set_auth_token(r.session.access_token)",
        "fid = db.get_profile(r.user.id)['family_id']",
        "t = db.get_client().table",
        "for p in t('projects').select('id').eq('family_id', fid).eq('name', 'NET-PROJ').execute().data: print('deleted', db.delete_project(p['id'], fid))",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
