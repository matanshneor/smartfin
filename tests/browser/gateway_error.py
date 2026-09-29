"""בדיקת דפדפן אמיתי: שמירה שקיבלה דף שגיאה (502) לא אומרת "שגיאת רשת — נסה שוב" (ב12-3).

לא נאספת על ידי pytest (אין לה קידומת test_), כי היא מרימה שרת מקומי,
מתחברת כמשתמש הבדיקה א'; תשובת השמירה מדומה ב-Playwright, אז דבר לא נכתב. תשובות השרת לבקשות האיטיות מדומות ב-Playwright.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/gateway_error.py
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
        rc = page.request.post(BASE + "/api/categories", data=json.dumps(
            {"name": "SCANTEST-CAT", "icon": "🧪", "type": "expense"}), headers={"Content-Type": "application/json"})
        page.route("**/api/transactions", lambda route: route.fulfill(
            status=502, content_type="text/html", body="<html><body>Application failed to respond</body></html>")
            if route.request.method == "POST" else route.continue_())
        page.goto(BASE + "/settings")
        page.click("#fabBtn"); page.wait_for_selector("#modalOverlay.open")
        page.fill("#txAmount", "44"); page.click("#submitBtn"); page.wait_for_timeout(1500)
        msg = page.text_content("#formError")
        print("message:", repr(msg))
        print("   honest:", "ייתכן" in msg and "רשת" not in msg)
        page.request.fetch(BASE + "/api/categories", method="GET")
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
