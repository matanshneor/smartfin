"""בדיקת דפדפן אמיתי: הסרת בן משפחה מוסתרת תחת "אפשרויות מתקדמות",
ושלוש שאלות קודמות לה — נסיגה בכל אחת מהן לא שולחת כלום.

מעבירה זמנית את משתמש הבדיקה ב' למשפחה של א' (SQL בהרשאות בעלים, כמו
test_family_join) ומחזירה אותו בסוף. בקשת ההסרה עצמה נעצרת בדפדפן ולא
מגיעה לשרת — שום הסרה אמיתית לא מתבצעת.

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/remove_member_hidden.py
"""
import os, json, time, subprocess, signal
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
EMAIL_A = env.get("RLS_TEST_EMAIL_A", "rls-test-family-a@smartfin.test")
EMAIL_B = env.get("RLS_TEST_EMAIL_B", "rls-test-family-b@smartfin.test")


def sql(q):
    out = subprocess.run(["supabase", "db", "query", q, "--linked", "-o", "json"],
                         cwd=os.path.join(ROOT, "backend"), capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[:300])
    txt = out.stdout
    return json.loads(txt[txt.index("{"):])["rows"]


ids = sql(f"select u.email, p.id, p.family_id from auth.users u join profiles p on p.id = u.id "
          f"where u.email in ('{EMAIL_A}', '{EMAIL_B}')")
a = next(r for r in ids if r["email"] == EMAIL_A)
b = next(r for r in ids if r["email"] == EMAIL_B)
manager = sql(f"select manager_id from families where id = '{a['family_id']}'")[0]["manager_id"]
print("A is manager:", manager == a["id"])
sql(f"update profiles set family_id = '{a['family_id']}' where id = '{b['id']}'")

srv = subprocess.Popen([os.path.join(ROOT, ".venv/bin/python3"), "-m", "backend.app"], cwd=ROOT, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
BASE = "http://127.0.0.1:8099"
try:
    for _ in range(40):
        try:
            import urllib.request; urllib.request.urlopen(BASE + "/health", timeout=1); break
        except Exception: time.sleep(0.5)
    with sync_playwright() as p:
        br = p.chromium.launch()
        page = br.new_page(viewport={"width": 390, "height": 844})
        page.goto(BASE + "/login")
        page.fill("#identifier", EMAIL_A)
        page.fill("#password", env["RLS_TEST_PASSWORD_A"])
        page.click("button.submit-btn")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        sent = []
        def hold(route):
            sent.append(route.request.post_data)
            route.fulfill(status=200, content_type="application/json", body='{"status":"ok"}')
        page.route("**/api/family/members/**", hold)

        page.goto(BASE + "/settings")
        # קבוצת "המשפחה שלי" בהגדרות מקופלת; פותחים אותה כמו משתמש
        page.click("button:has(.group-title:text-is('המשפחה שלי'))")
        page.wait_for_timeout(400)
        print("icon next to members:", page.locator(".remove-member-btn").count())
        print("remove button visible before opening:", page.is_visible("#removeMemberBtn"))
        page.click(".advanced-summary")
        print("visible after opening:", page.is_visible("#removeMemberBtn"),
              "| options:", page.eval_on_selector_all("#removeMemberSelect option", "os => os.map(o => o.textContent.trim())"))

        def dialog():
            page.wait_for_selector("#confirmOverlay.open", timeout=5000)
            return page.inner_text("#confirmTitle")

        def answer(sel):
            # השאלה הבאה נפתחת מיד אחרי הקודמת, אז לא מחכים לסגירה
            page.click(sel)
            page.wait_for_timeout(400)

        # נסיגה בכל אחת משלוש השאלות
        for stop_at in (1, 2, 3):
            page.click("#removeMemberBtn")
            titles = [dialog()]
            if stop_at == 1:
                answer("#confirmNo")
            else:
                answer("#confirmYes")
                titles.append(dialog())
                if stop_at == 2:
                    page.evaluate("document.getElementById('confirmOverlay').click()")  # נסיגה
                    page.wait_for_timeout(300)
                else:
                    answer("#confirmNo")            # "להשאיר כמשותפות"
                    titles.append(dialog())
                    answer("#confirmNo")            # ביטול באישור האחרון
            print(f"stop at {stop_at}: {titles} → sent {len(sent)}")

        # עד הסוף
        page.click("#removeMemberBtn"); dialog(); answer("#confirmYes")
        dialog(); answer("#confirmNo")
        print("final:", dialog(), "|", page.inner_text("#confirmMessage"))
        page.screenshot(path="/tmp/remove_final.png")
        answer("#confirmYes")
        page.wait_for_timeout(500)
        print("sent after confirming:", sent)
        br.close()
finally:
    sql(f"update profiles set family_id = '{b['family_id']}' where id = '{b['id']}'")
    back = sql(f"select family_id from profiles where id = '{b['id']}'")[0]["family_id"]
    print("B restored:", back == b["family_id"])
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)
