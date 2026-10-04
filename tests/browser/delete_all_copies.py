"""בדיקת דפדפן אמיתי: מחיקה בעמוד החודש מסירה את כל העותקים של העסקה (ב12-7).

לא נאספת על ידי pytest (אין לה קידומת test_), כי היא מרימה שרת מקומי,
מתחברת כמשתמש הבדיקה א' (RLS_TEST_* ב-.env) וכותבת למסד האמיתי — ומנקה
אחריה. תשובות השרת לבקשות האיטיות מדומות ב-Playwright.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/delete_all_copies.py
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
        if "/onboarding" in page.url:
            print("NOTE: test user lands on onboarding"); 
        today = datetime.date.today().isoformat()
        rc = page.request.post(BASE + "/api/categories", data=json.dumps(
            {"name": "SCANTEST-CAT", "icon": "🧪", "type": "expense"}),
            headers={"Content-Type": "application/json"})
        cat = (rc.json().get("category") or rc.json()).get("id")
        print("temp category:", rc.status, bool(cat))
        r = page.request.post(BASE + "/api/transactions", data=json.dumps(
            {"amount": "65", "type": "expense", "date": today, "description": "COPIES", "category_id": cat}),
            headers={"Content-Type": "application/json"})
        tid = r.json().get("transaction", r.json()).get("id")
        page.goto(BASE + "/month")
        copies = lambda: page.evaluate("(id) => document.querySelectorAll('[data-id=\"' + id + '\"]').length", tid)
        before = copies()
        page.click(".all-tx-header")
        page.locator(f'.cat-tx-row[data-id="{tid}"]').locator("visible=true").first.click()
        page.wait_for_selector("#modalOverlay.open")
        page.click("#deleteTxBtn")
        page.wait_for_selector("#confirmOverlay.open"); page.click("#confirmYes")
        page.wait_for_timeout(1500)                     # לפני הרענון של אחרי 6 שניות
        after = copies()
        print(f"copies on the page: before {before}, right after delete {after}")
        print("   all gone:", before > 1 and after == 0)
        b.close()
finally:
    # ניקוי: כל מה שהתסריט יצר במשפחת הבדיקה — גם אם הוא נפל באמצע.
    # קוד רגיל ולא מחרוזת משורשרת: הגרסה הקודמת נשברה על ‎created = None‎
    # ("invalid input syntax for type uuid") והשאירה שאריות לריצה הבאה.
    cleanup = "\n".join([
        "import os, sys",
        "sys.path.insert(0, '.')",
        "from dotenv import load_dotenv; load_dotenv('.env')",
        "from backend import supabase_config as db",
        "r, _ = db.sign_in(os.environ.get('RLS_TEST_EMAIL_A', 'rls-test-family-a@smartfin.test'), os.environ['RLS_TEST_PASSWORD_A'])",
        "db.set_auth_token(r.session.access_token)",
        "fid = db.get_profile(r.user.id)['family_id']",
        "t = db.get_client().table",
        "t('transactions').delete().eq('family_id', fid).in_('description', "
        "['SUPER-ORIG', 'FIRST', 'THIRD', 'CHART-1', 'CHART-2', 'PAST-ADD', 'ROW-A', 'ROW-B', 'COPIES']).execute()",
        "t('categories').delete().eq('family_id', fid).eq('name', 'SCANTEST-CAT').execute()",
        "print('cleaned')",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)   # תהליך-הבן של Flask נסגר רגע אחרי
