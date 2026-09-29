"""בדיקת דפדפן אמיתי: שינויים בקטגוריות בהגדרות: מגיעים ל-+, ושינוי שם לא מעלים את התקציב (ב11).

לא נאספת על ידי pytest (אין לה קידומת test_), כי היא מרימה שרת מקומי,
מתחברת כמשתמש הבדיקה א' (RLS_TEST_* ב-.env) וכותבת למסד האמיתי — ומנקה
אחריה. תשובות השרת לבקשות האיטיות מדומות ב-Playwright.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/settings_categories.py
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
        page.goto(BASE + "/settings")
        page.locator(".settings-group-header", has_text="קטגוריות").first.click()
        page.click("#manageCatsBtn")
        in_plus = lambda: page.evaluate("""() => [...document.querySelectorAll('#categoryGrid .cat-btn')]
                                           .map(b => b.textContent.trim())""")

        # הטופס נפתח פעם אחת לפני השינוי — כך המטמון שלו כבר מלא, כמו אצל משתמש
        page.click("#fabBtn"); page.wait_for_selector("#modalOverlay.open"); page.click("#modalClose")

        page.fill("#newCatName", "PETS-TEST"); page.fill("#newCatIcon", "🐶")
        page.click("#addCatForm button[type=submit]"); page.wait_for_timeout(1500)
        row = page.locator('.category-row[data-name="PETS-TEST"]')
        print("new row has budget control:", row.locator(".budget-enabled").count() == 1)
        page.click("#fabBtn"); page.wait_for_selector("#modalOverlay.open")
        print("new category in +:", any("PETS-TEST" in c for c in in_plus()))
        page.click("#modalClose")

        row.locator(".edit-cat-btn").click()
        page.fill('.category-row.editing .cat-edit-name', "PETS-RENAMED")
        page.click(".category-row.editing .cat-edit-save"); page.wait_for_timeout(1500)
        renamed = page.locator('.category-row[data-name="PETS-RENAMED"]')
        print("renamed row keeps budget control:", renamed.locator(".budget-enabled").count() == 1,
              "| name shown:", renamed.locator(".cat-row-name").text_content())
        page.click("#fabBtn"); page.wait_for_selector("#modalOverlay.open")
        print("renamed category in +:", any("PETS-RENAMED" in c for c in in_plus()))
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
        "['SUPER-ORIG', 'FIRST', 'THIRD', 'CHART-1', 'CHART-2', 'PAST-ADD', 'ROW-A', 'ROW-B', 'SWIPE-RENT']).execute()",
        "t('categories').delete().eq('family_id', fid).in_('name', ['SCANTEST-CAT', 'PETS-TEST', 'PETS-RENAMED']).execute()",
        "print('cleaned')",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)   # תהליך-הבן של Flask נסגר רגע אחרי
