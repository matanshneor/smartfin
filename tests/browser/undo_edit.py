"""בדיקת דפדפן אמיתי: "בטל" אחרי עריכה — בחלון, בשורה בדף הבית, ובלי לדרוס שינוי של אחר (מתן, 30.9 — סבב 6, פריט 10).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/undo_edit.py
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

        cat = next(c["id"] for c in page.request.get(BASE + "/api/categories").json() if c["type"] == "expense")
        _, made = api("POST", "/api/transactions", {"amount": 230, "type": "expense", "category_id": cat,
                                                    "date": datetime.date.today().isoformat(), "description": "UN-TEST קנייה"})
        tid = (made.get("transaction") or made)["id"]
        amount_now = lambda: next(t["amount"] for t in page.request.get(BASE + "/api/search?q=UN-TEST").json()["results"])

        # 1. עמוד החודש — חלון עריכה
        page.goto(BASE + "/month"); page.wait_for_timeout(1200)
        page.click(".all-tx-header"); page.wait_for_timeout(300)
        page.locator(f'.cat-tx-row[data-id="{tid}"]:visible').first.click(); page.wait_for_timeout(1200)
        page.fill("#txAmount", "320"); page.click("#submitBtn"); page.wait_for_timeout(2800)
        print("month — toast:", page.locator("#appToast .toast-msg").inner_text(), "|", page.locator("#appToast .toast-action").inner_text(), "| now:", amount_now())
        page.screenshot(path="/tmp/undo_toast.png")
        page.click("#appToast .toast-action"); page.wait_for_timeout(2800)
        print("month — after בטל:", amount_now(), "|", page.locator("#appToast .toast-msg").inner_text())

        # 2. דף הבית — עריכה בתוך השורה
        page.goto(BASE + "/"); page.wait_for_timeout(1000)
        page.locator(f'.transaction-item[data-id="{tid}"] .tx-head').click(); page.wait_for_timeout(1200)
        row = page.locator(f'.transaction-item[data-id="{tid}"]')
        row.locator('input[inputmode="decimal"], input[type="number"]').first.fill("410")
        row.locator("button", has_text="שמור").click(); page.wait_for_timeout(3000)
        print("home — toast:", page.locator("#appToast .toast-msg").inner_text(), "| action:", page.locator("#appToast .toast-action").count(), "| now:", amount_now())
        page.click("#appToast .toast-action"); page.wait_for_timeout(3000)
        print("home — after בטל:", amount_now())

        # 3. מישהו שינה בינתיים — "בטל" לא דורס
        page.goto(BASE + "/month"); page.wait_for_timeout(1200)
        page.click(".all-tx-header"); page.wait_for_timeout(300)
        page.locator(f'.cat-tx-row[data-id="{tid}"]:visible').first.click(); page.wait_for_timeout(1200)
        page.fill("#txAmount", "500"); page.click("#submitBtn"); page.wait_for_timeout(2800)
        api("PUT", f"/api/transactions/{tid}", {"amount": 555, "type": "expense", "category_id": cat,
                                               "date": datetime.date.today().isoformat(), "description": "UN-TEST קנייה"})
        page.click("#appToast .toast-action"); page.wait_for_timeout(1500)
        print("conflict — message:", page.locator("#appToast .toast-msg").inner_text(), "| kept:", amount_now())
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
        "print('cleaned', len(t('transactions').delete().eq('family_id', fid).like('description', 'UN-TEST%').execute().data))",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
