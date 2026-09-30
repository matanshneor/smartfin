"""בדיקת דפדפן אמיתי: סינון "כל העסקאות" לפי סוג בעמוד החודש (מתן, 30.9 — רעיון 5).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/type_filter.py
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

        cats = page.request.get(BASE + "/api/categories").json()
        by = {t: next(c["id"] for c in cats if c["type"] == t) for t in ("expense", "income", "savings")}
        today = datetime.date.today().isoformat()
        for kind, amount, desc in (("expense", 100, "TF-TEST סופר"), ("expense", 50, "TF-TEST דלק"),
                                   ("income", 5000, "TF-TEST משכורת"), ("savings", 700, "TF-TEST קרן")):
            api("POST", "/api/transactions", {"amount": amount, "type": kind, "category_id": by[kind],
                                              "date": today, "description": desc})
        page.goto(BASE + "/month"); page.wait_for_timeout(1500)
        page.click(".all-tx-header"); page.wait_for_timeout(300)
        chips = page.locator(".tx-type-chip")
        print("chips:", chips.all_inner_texts())
        visible = lambda: page.locator(".all-tx-header + .tx-search-wrap + .cat-tx-list .cat-tx-row:visible").count()
        count = lambda: page.locator(".all-tx-count").inner_text()
        print("all:", visible(), count())
        for label in ("הוצאות", "הכנסות", "חיסכון"):
            page.locator(".tx-type-chip", has_text=label).click(); page.wait_for_timeout(150)
            types = page.locator(".all-tx-header + .tx-search-wrap + .cat-tx-list .cat-tx-row:visible").evaluate_all(
                "els => [...new Set(els.map(e => e.dataset.type))]")
            print(label, "->", visible(), count(), types)
        page.locator(".tx-type-chip", has_text="הוצאות").click()
        page.fill("#txSearch", "דלק"); page.wait_for_timeout(150)
        print("הוצאות + דלק ->", visible(), count())
        page.fill("#txSearch", "משכורת"); page.wait_for_timeout(150)
        print("הוצאות + משכורת ->", visible(), "| empty msg:", page.locator("#txSearchEmpty").is_visible())
        page.fill("#txSearch", ""); page.locator(".tx-type-chip", has_text="הכל").click(); page.wait_for_timeout(150)
        print("back to all:", visible(), count(), "| open still:",
              page.locator(".all-tx-header").get_attribute("aria-expanded"))
        page.locator(".tx-type-chip", has_text="הוצאות").click(); page.wait_for_timeout(150)
        for w in (320, 390):
            page.set_viewport_size({"width": w, "height": 800}); page.wait_for_timeout(300)
            print(w, "sideways:", page.evaluate("document.documentElement.scrollWidth > innerWidth"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator(".all-tx-header").scroll_into_view_if_needed()
        page.screenshot(path="/tmp/type_filter.png")
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
        "print('cleaned', len(t('transactions').delete().eq('family_id', fid).like('description', 'TF-TEST%').execute().data))",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
