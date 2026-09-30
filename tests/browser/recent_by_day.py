"""בדיקת דפדפן אמיתי: "עסקאות אחרונות" מחולקות לפי יום (מתן, 30.9 — רעיון 2).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/recent_by_day.py
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

        def api(method, url, body=None):
            r = page.request.fetch(BASE + url, method=method, data=json.dumps(body) if body else None,
                                   headers={"Content-Type": "application/json"})
            return r.status, (r.json() if r.body() else None)

        cat = next(c["id"] for c in page.request.get(BASE + "/api/categories").json() if c["type"] == "expense")
        today = datetime.date.today()
        for days, amount, desc in ((0, 320, "DAY-TEST רמי לוי"), (0, 250, "DAY-TEST"), (1, 18, "DAY-TEST קפה"),
                                   (3, 90, "DAY-TEST")):
            api("POST", "/api/transactions", {"amount": amount, "type": "expense", "category_id": cat,
                                              "date": (today - datetime.timedelta(days=days)).isoformat(),
                                              "description": desc})
        page.goto(BASE + "/"); page.wait_for_timeout(1500)
        print("days:", page.locator(".tx-day").all_inner_texts())
        # הוספה דרך הטופס: השורה הזמנית נכנסת מתחת ל"היום"
        page.click("#fabBtn") if page.locator("#fabBtn").count() else page.click(".fab")
        page.wait_for_timeout(800)
        page.fill("#txAmount", "77")
        page.fill("#txDescription", "DAY-TEST חדשה")
        page.click("#submitBtn")
        page.wait_for_timeout(150)
        first_two = page.locator(".transactions-list > li").evaluate_all(
            "els => els.slice(0,2).map(e => e.className + ' | ' + e.innerText.split('\\n')[0])")
        print("right after add:", first_two)
        page.wait_for_timeout(2500)
        print("after refresh:", page.locator(".tx-day").all_inner_texts())
        for w in (320, 390):
            page.set_viewport_size({"width": w, "height": 800}); page.wait_for_timeout(300)
            print(w, "sideways:", page.evaluate("document.documentElement.scrollWidth > innerWidth"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator(".transactions-section").scroll_into_view_if_needed()
        page.screenshot(path="/tmp/recent_by_day.png")
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
        "print('cleaned', len(t('transactions').delete().eq('family_id', fid).like('description', 'DAY-TEST%').execute().data))",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
