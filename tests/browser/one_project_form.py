"""בדיקת דפדפן אמיתי: טופס אחד ליצירת פרויקט — מההגדרות מגיעים אליו פתוח (מתן, 30.9 — רעיון 13).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/one_project_form.py
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
        r = page.request.fetch(BASE + "/api/projects", method="POST",
                               data=json.dumps({"name": "PJ-קיים", "track_expense": True}),
                               headers={"Content-Type": "application/json"})
        print("seed project:", r.status)

        page.goto(BASE + "/settings"); page.wait_for_timeout(1000)
        link = page.locator("a", has_text="יצירת פרויקט חדש")
        link.evaluate("el => el.closest('.settings-group').querySelector('button').click()")
        page.wait_for_timeout(400)
        print("old settings form gone:", page.locator("#newProjectSettingsForm").count() == 0)
        # עריכה במקום עדיין עובדת
        page.locator(".edit-project-settings-btn").first.click(); page.wait_for_timeout(300)
        print("edit in settings still opens:", page.locator(".project-settings-row.editing").count())
        link.click(); page.wait_for_timeout(1500)
        print("landed:", page.url.replace(BASE, ""))
        print("form open:", page.locator("#newProjectForm").is_visible(),
              "| focused:", page.evaluate("document.activeElement.id"),
              "| icon field:", page.locator("#projectIcon").is_visible(),
              "| description:", page.locator("#projectDescription").is_visible())
        page.screenshot(path="/tmp/new_project.png")
        page.goto(BASE + "/projects"); page.wait_for_timeout(800)
        print("without #new the form stays closed:", not page.locator("#newProjectForm").is_visible())
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
        "print('projects', len(t('projects').delete().eq('family_id', fid).like('name', 'PJ-%').execute().data))",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
