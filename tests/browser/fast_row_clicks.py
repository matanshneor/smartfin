"""בדיקת דפדפן אמיתי: לחיצה מהירה על שתי עסקאות: הלחיצה האחרונה קובעת (ב8).

לא נאספת על ידי pytest (אין לה קידומת test_), כי היא מרימה שרת מקומי,
מתחברת כמשתמש הבדיקה א' (RLS_TEST_* ב-.env) וכותבת למסד האמיתי — ומנקה
אחריה. תשובות השרת לבקשות האיטיות מדומות ב-Playwright.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/fast_row_clicks.py
"""
import os, json, time, datetime, subprocess, signal
from playwright.sync_api import sync_playwright
import _accounts  # noqa: F401 — חשבונות בדיקה זמניים, נמחקים בסוף הריצה

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
        ids = {}
        for desc, amount in (("ROW-A", "180"), ("ROW-B", "250")):
            r = page.request.post(BASE + "/api/transactions", data=json.dumps(
                {"amount": amount, "type": "expense", "date": today, "description": desc, "category_id": cat}),
                headers={"Content-Type": "application/json"})
            ids[desc] = r.json().get("transaction", r.json()).get("id")

        held = []
        def hold(route): held.append(route)
        def row(desc):
            return page.locator(f'.cat-tx-row[data-id="{ids[desc]}"]').locator("visible=true").first
        def form():
            return page.evaluate("""() => ({open: modalOverlay.classList.contains('open'),
                title: document.getElementById('modalTitle').textContent,
                amount: txAmount.value, desc: txDescription.value})""")
        def release_newest_first():
            """התשובה של הלחיצה הראשונה מגיעה אחרונה — וזה מובטח, לא מקרי:
            התשובות האמיתיות נאספות מהשרת קודם, ונמסרות לדפדפן אחת-אחת."""
            page.wait_for_timeout(300)
            answers = [(r, r.fetch()) for r in held]
            for r, resp in reversed(answers):
                r.fulfill(response=resp)
                page.wait_for_timeout(500)
            held.clear()
            page.wait_for_timeout(1000)

        # ── 1. עסקה א', ומיד עסקה ב' — והתשובות של א' מגיעות אחרונות
        page.route("**/api/categories", hold)
        page.goto(BASE + "/month")
        page.click("#txScreenOpen")      # "כל העסקאות" — הרשימה מקופלת
        row("ROW-A").click(); row("ROW-B").click()
        release_newest_first()
        f = form()
        print("A then B:", f)
        print("   shows B:", f["open"] and f["desc"] == "ROW-B" and f["amount"] in ("250", "250.0"))
        page.fill("#txAmount", "251"); page.click("#submitBtn"); page.wait_for_timeout(2500)
        rows = page.evaluate("""(ids) => ids.map(id => {
            const el = document.querySelector('.cat-tx-row[data-id="' + id + '"]');
            return el ? el.dataset.amount + ' ' + el.dataset.description : null; })""", [ids["ROW-A"], ids["ROW-B"]])
        # סכום **ותיאור**: הגרסה הקודמת של הבדיקה בדקה רק סכום, ואישרה בטעות
        # את "251 ROW-A" — ב' שנדרס בתיאור של א'.
        print("   after save:", rows, "->",
              "OK" if rows == ["180.0 ROW-A", "251.0 ROW-B"] else "WRONG")

        # ── 2. עסקה, ומיד + — והתשובות של העסקה מגיעות אחרונות
        page.goto(BASE + "/month")        # מטמון ריק מחדש
        page.click("#txScreenOpen")
        row("ROW-A").click(); page.click("#fabBtn")
        release_newest_first()
        f = form()
        print("row then +:", f)
        print("   empty add form:", f["open"] and f["title"] == "הוספת עסקה" and f["amount"] == "" and f["desc"] == "")
        page.click("#modalClose")
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
        "['SUPER-ORIG', 'FIRST', 'THIRD', 'CHART-1', 'CHART-2', 'PAST-ADD', 'ROW-A', 'ROW-B']).execute()",
        "t('categories').delete().eq('family_id', fid).eq('name', 'SCANTEST-CAT').execute()",
        "print('cleaned')",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)   # תהליך-הבן של Flask נסגר רגע אחרי
