"""בדיקת דפדפן אמיתי: כרטיס "תקציבים החודש" בדף הבית (מתן, 30.9 — אפשרות א).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/home_budgets.py
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


chosen = []
original = {}
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

        page.goto(BASE + "/"); page.wait_for_timeout(800)
        print("before (no budgets expected unless the test family has some):",
              page.locator(".home-budgets").count())

        cats = [c for c in page.request.get(BASE + "/api/categories").json() if c["type"] == "expense"][:3]
        for name, icon in (("HB-דלק", "⛽"), ("HB-מסעדות", "🍽")):
            if len(cats) >= 3: break
            _, c2 = api("POST", "/api/categories", {"name": name, "icon": icon, "type": "expense"})
            cats.append(c2.get("category") or c2)
        chosen = [c["id"] for c in cats]
        today = datetime.date.today().isoformat()
        # אחת בחריגה, אחת ב-88%, אחת ב-48%
        plan = ((cats[0], 500, 650), (cats[1], 2000, 1760), (cats[2], 800, 380))
        print("set limits:", api("PUT", "/api/family/settings",
              {"limits": {c["id"]: {"amount": lim, "alert": False} for c, lim, _ in plan}})[0])
        for c, _, spent in plan:
            api("POST", "/api/transactions", {"amount": spent, "type": "expense", "date": today,
                                              "description": "HB-TEST", "category_id": c["id"]})
        page.goto(BASE + "/"); page.wait_for_timeout(1500)
        card = page.locator(".home-budgets")
        print("names:", card.locator(".home-budget-name").all_inner_texts())
        print("left:", card.locator(".home-budget-left").all_inner_texts())
        print("fills:", [e.get_attribute("class") for e in card.locator(".home-budget-fill").all()])
        for w in (320, 390):
            page.set_viewport_size({"width": w, "height": 800}); page.wait_for_timeout(300)
            print(w, "sideways:", page.evaluate("document.documentElement.scrollWidth > innerWidth"))
        page.set_viewport_size({"width": 390, "height": 844}); card.scroll_into_view_if_needed()
        page.screenshot(path="/tmp/home_budgets.png")
        card.locator(".see-all-link").click(); page.wait_for_timeout(1200)
        print("link ->", page.url)
        # מסירים את התקציבים שקבענו
        print("unset:", api("PUT", "/api/family/settings", {"limits": {cid: None for cid in chosen}})[0])
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
        "print('cleaned', len(t('transactions').delete().eq('family_id', fid).eq('description', 'HB-TEST').execute().data))",
        "t('categories').delete().eq('family_id', fid).like('name', 'HB-%').execute()",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
