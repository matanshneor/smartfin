"""בדיקת דפדפן אמיתי: סריקת קבלה שחוזרת לטופס שכבר נסגר או הוחלף (ב1).

לא נאספת על ידי pytest (אין לה קידומת test_), כי היא מרימה שרת מקומי,
מתחברת כמשתמש הבדיקה א' (RLS_TEST_* ב-.env) וכותבת למסד האמיתי — ומנקה
אחריה. תשובות השרת לבקשות האיטיות מדומות ב-Playwright.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/scan_race.py
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
        r = page.request.post(BASE + "/api/transactions", data=json.dumps(
            {"amount": "180", "type": "expense", "date": today, "description": "SUPER-ORIG", "category_id": cat}),
            headers={"Content-Type": "application/json"})
        created = r.json().get("transaction", r.json()).get("id")
        print("created tx:", r.status, bool(created))
        fid = page.evaluate("() => document.cookie") and None

        discards = []
        def scan_route(route):
            time.sleep(2.5)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"amount": 999, "merchant": "SCANNED-MERCHANT", "date": "2026-01-15",
                 "receipt_path": "FAMILY/fake-scan.jpg"}))
        page.route("**/api/receipts/scan", scan_route)
        page.route("**/api/receipts/discard", lambda route: (
            discards.append(json.loads(route.request.post_data)["path"]),
            route.fulfill(status=200, content_type="application/json", body='{"status":"ok"}')))

        page.on("console", lambda m: print("   ", m.text) if "DBG" in m.text else None)
        page.goto(BASE + "/")
        vals = lambda: page.evaluate("""() => ({amount: txAmount.value, desc: txDescription.value,
                     date: txDate.value, receipt: txReceiptPath.value,
                     open: document.getElementById('modalOverlay').classList.contains('open')})""")

        # ── 1. הבאג: סריקה ← סגירה ← עריכת עסקה קיימת ← התשובה חוזרת
        page.click("#fabBtn"); page.wait_for_selector("#modalOverlay.open")
        page.set_input_files("#receiptInput", JPEG)
        page.click("#modalClose")
        print("   url:", page.url, "| rows with id:", page.locator(f'[data-id="{created}"]').count(),
              "| visible:", [page.locator(f'[data-id="{created}"]').nth(i).is_visible() for i in range(page.locator(f'[data-id="{created}"]').count())])
        page.screenshot(path="/tmp/before_row_click.png")
        page.locator(f'[data-id="{created}"]').first.click()      # עורך בשורה
        page.locator(".inline-more").first.click()                   # "עוד אפשרויות" → החלון המלא
        page.wait_for_selector("#modalOverlay.open", timeout=5000)
        page.wait_for_timeout(4000)
        v = vals()
        print("1) edit form after stale scan:", v)
        print("   untouched:", v["amount"] in ("180", "180.0") and v["desc"] == "SUPER-ORIG" and v["receipt"] == "")
        print("   discarded stale upload:", discards)
        page.click("#modalClose"); discards.clear()

        # ── 2. בקרה: סריקה רגילה נכנסת לטופס, ונטישה מוחקת את התמונה
        page.click("#fabBtn"); page.wait_for_selector("#modalOverlay.open")
        page.set_input_files("#receiptInput", JPEG)
        page.wait_for_timeout(4000)
        print("   discards before closing:", list(discards))
        v = vals()
        print("2) add form after normal scan:", {k: v[k] for k in ("amount", "desc", "receipt")})
        page.click("#modalClose"); time.sleep(0.5)
        print("   abandoned → discarded:", discards)
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
        "['SUPER-ORIG', 'FIRST', 'THIRD', 'CHART-1', 'CHART-2']).execute()",
        "t('categories').delete().eq('family_id', fid).eq('name', 'SCANTEST-CAT').execute()",
        "print('cleaned')",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)   # תהליך-הבן של Flask נסגר רגע אחרי
