"""בדיקת דפדפן אמיתי: חודש עתידי נראה כמו כל חודש, עם העסקאות הקבועות שייפלו בו (מתן, 30.9 — רעיון 6).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/future_month.py
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

        cats = page.request.get(BASE + "/api/categories").json()
        by = {t: next(c["id"] for c in cats if c["type"] == t) for t in ("expense", "income")}
        today = datetime.date.today()
        for kind, amount, desc, freq in (("expense", 5500, "FUT-TEST שכר דירה", "monthly_same"),
                                         ("expense", 300, "FUT-TEST גן", "weekly"),
                                         ("income", 8000, "FUT-TEST משכורת", "monthly_same")):
            print("add", desc, api("POST", "/api/transactions", {
                "amount": amount, "type": kind, "category_id": by[kind], "date": today.isoformat(),
                "description": desc, "is_recurring": True, "recurring_frequency": freq})[0])
        y, m = today.year, today.month + 2
        if m > 12: y, m = y + 1, m - 12
        page.goto(f"{BASE}/month?year={y}&month={m}"); page.wait_for_timeout(1500)
        print("empty text:", page.locator("text=לא נרשמו עסקאות").count())
        print("net:", page.locator(".month-net").inner_text().replace("\n", " | "))
        print("chips:", page.locator(".kpi-chips-three").inner_text().replace("\n", " | "))
        page.click(".all-tx-header"); page.wait_for_timeout(300)
        rows = page.locator(".all-tx-header + .tx-search-wrap + .cat-tx-list .cat-tx-row")
        print("all rows:", rows.evaluate_all("els => els.map(e => e.querySelector('.cat-tx-date').innerText + ' ' + e.querySelector('.cat-tx-desc').innerText.replace('FUT-TEST ', '') + ' id=' + JSON.stringify(e.dataset.id))"))
        rows.first.click(); page.wait_for_timeout(700)
        print("modal opened on click:", page.locator("#txModal.open, .modal.open, .modal-overlay.open").count())
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path="/tmp/future_month.png")
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
        "print('cleaned', len(t('transactions').delete().eq('family_id', fid).like('description', 'FUT-TEST%').execute().data))",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
