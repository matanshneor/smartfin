"""בדיקת דפדפן אמיתי: באנר ההתקנה נשאר אחרי הוספת עסקה בדף הבית (ב12-6).

לא נאספת על ידי pytest (אין לה קידומת test_), כי היא מרימה שרת מקומי,
מתחברת כמשתמש הבדיקה א'; בזהות של אייפון, כדי שהבאנר יציג את הנחיית ההתקנה של iOS. תשובות השרת לבקשות האיטיות מדומות ב-Playwright.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/install_banner.py
"""
import os, json, time, datetime, subprocess, signal
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
        ctx = b.new_context(viewport={"width": 390, "height": 844}, user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"))
        page = ctx.new_page()
        page.goto(BASE + "/login")
        page.fill("#identifier", env.get("RLS_TEST_EMAIL_A", "rls-test-family-a@smartfin.test"))
        page.fill("#password", env["RLS_TEST_PASSWORD_A"])
        page.click("button.submit-btn")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        rc = page.request.post(BASE + "/api/categories", data=json.dumps(
            {"name": "SCANTEST-CAT", "icon": "🧪", "type": "expense"}), headers={"Content-Type": "application/json"})
        page.request.post(BASE + "/api/transactions", data=json.dumps(
            {"amount": "10", "type": "expense", "date": datetime.date.today().isoformat(), "description": "BANNER-SEED"}),
            headers={"Content-Type": "application/json"})
        page.goto(BASE + "/")
        shown = lambda: page.evaluate("""() => { const b = document.getElementById('installBanner');
            return b && b.style.display !== 'none' ? document.getElementById('installBannerText').textContent : null; }""")
        before = shown()
        page.click("#fabBtn"); page.wait_for_selector("#modalOverlay.open")
        page.fill("#txAmount", "11"); page.fill("#txDescription", "BANNER-ADD")
        page.click("#submitBtn"); page.wait_for_timeout(3000)
        after = shown()
        print("banner before:", repr(before), "| after adding:", repr(after))
        print("   still there:", bool(before) and after == before)
        b.close()
finally:
    import subprocess as _sp
    _sp.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", "\n".join([
        "import os, sys", "sys.path.insert(0, '.')", "from dotenv import load_dotenv; load_dotenv('.env')",
        "from backend import supabase_config as db",
        "r, _ = db.sign_in(os.environ.get('RLS_TEST_EMAIL_A', 'rls-test-family-a@smartfin.test'), os.environ['RLS_TEST_PASSWORD_A'])",
        "db.set_auth_token(r.session.access_token)", "fid = db.get_profile(r.user.id)['family_id']",
        "db.get_client().table('categories').delete().eq('family_id', fid).eq('name', 'SCANTEST-CAT').execute()",
        "db.get_client().table('transactions').delete().eq('family_id', fid).in_('description', ['BANNER-SEED', 'BANNER-ADD']).execute()"])], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)   # תהליך-הבן של Flask נסגר רגע אחרי
