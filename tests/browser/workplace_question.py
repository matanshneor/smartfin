"""בדיקת דפדפן אמיתי: שאלת מקום העבודה: יציאה מבטלת, ואחרי שמירה היא לא חוזרת בלי שינוי (ב12-4).

לא נאספת על ידי pytest (אין לה קידומת test_), כי היא מרימה שרת מקומי,
מתחברת כמשתמש הבדיקה א'; שמירת הפרופיל מדומה ב-Playwright, אז הפרופיל לא משתנה. תשובות השרת לבקשות האיטיות מדומות ב-Playwright.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/workplace_question.py
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
JPEG = "/tmp/tiny.jpg"
open(JPEG, "wb").write(bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9"))
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
        puts = []
        def profile(route):
            body = json.loads(route.request.post_data)
            puts.append(body.get("workplace_scope"))
            route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"status": "ok", "full_name": "בדיקה", "phone": "", "workplace": body.get("workplace")}))
        page.route("**/api/profile", profile)
        page.goto(BASE + "/settings")
        page.locator(".settings-group", has=page.locator("#editProfileBtn")).locator(".settings-group-header").click()
        dialog_open = lambda: page.evaluate("() => document.getElementById('confirmOverlay').classList.contains('open')")

        def save_with(workplace):
            if not page.is_visible("#editWorkplace"):
                page.click("#editProfileBtn")
            page.fill("#editWorkplace", workplace)
            page.click("#saveProfileBtn"); page.wait_for_timeout(600)

        # 1. יציאה מהשאלה
        save_with("WORK-X")
        asked = dialog_open()
        page.locator("#confirmYes").press("Escape"); page.wait_for_timeout(800)   # המיקוד בתוך החלון
        print("   dialog still open after Escape:", dialog_open())
        print(f"1) asked: {asked} | saves after Escape: {puts}  ->", "OK" if asked and puts == [] else "WRONG")
        # 2. בחירה אמיתית
        page.click("#saveProfileBtn"); page.wait_for_timeout(600)
        page.click("#confirmNo"); page.wait_for_timeout(800)
        print(f"2) saves after 'רק מהחודש הזה': {puts}  ->", "OK" if puts == ["future"] else "WRONG")
        # 3. שמירה נוספת בלי לשנות את מקום העבודה
        page.click("#editProfileBtn"); page.wait_for_timeout(300)
        page.click("#saveProfileBtn"); page.wait_for_timeout(800)
        asked_again = dialog_open()
        if asked_again: page.locator("#confirmYes").press("Escape")
        print(f"3) asked again with no change: {asked_again} | saves: {puts}  ->",
              "OK" if not asked_again and puts == ["future", None] else "WRONG")
        b.close()
finally:
    import subprocess as _sp
    _sp.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", "\n".join([
        "import os, sys", "sys.path.insert(0, '.')", "from dotenv import load_dotenv; load_dotenv('.env')",
        "from backend import supabase_config as db",
        "r, _ = db.sign_in(os.environ.get('RLS_TEST_EMAIL_A', 'rls-test-family-a@smartfin.test'), os.environ['RLS_TEST_PASSWORD_A'])",
        "db.set_auth_token(r.session.access_token)", "fid = db.get_profile(r.user.id)['family_id']",
        "db.get_client().table('categories').delete().eq('family_id', fid).eq('name', 'SCANTEST-CAT').execute()"])], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)   # תהליך-הבן של Flask נסגר רגע אחרי
