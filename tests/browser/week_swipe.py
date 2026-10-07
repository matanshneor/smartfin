"""בדיקת דפדפן אמיתי: החלקה בכרטיס "השבוע" לפי מהירות האצבע (מתן, 7.10 — עיצוב בנוסח אפל, סעיף 3).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/week_swipe.py

מדפיס PASS/FAIL לכל מקרה ויוצא עם קוד 1 אם משהו נכשל.
"""
import os, sys, json, time, datetime, subprocess, signal
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
                       start_new_session=True)
BASE = "http://127.0.0.1:8099"
failed = []

def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok: failed.append(name)

# מחווה מתוך הדף, תנועה כל ‎gap‎ ms (8 — מסך אמיתי; דרך CDP כל תנועה מתעכבת ~40ms)
GESTURE = """([xs, gap, hold]) => new Promise(done => {
    const card = document.querySelector('.week-card');
    const r = card.getBoundingClientRect();
    const x0 = r.left + r.width / 2, y0 = r.top + 30;
    const el = document.elementFromPoint(x0, y0);
    const at = dx => new Touch({ identifier: 1, target: el, clientX: x0 + dx, clientY: y0 });
    let last = at(0);
    const fire = (type, t) => el.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true,
        touches: t ? [t] : [], targetTouches: t ? [t] : [], changedTouches: [t || last] }));
    fire('touchstart', last);
    let i = 0;
    const tick = () => {
        if (i < xs.length) { last = at(xs[i]); fire('touchmove', last); i++; setTimeout(tick, gap); return; }
        setTimeout(() => { fire('touchend', null); done(); }, hold);
    };
    setTimeout(tick, gap);
})"""

try:
    for _ in range(40):
        try:
            import urllib.request; urllib.request.urlopen(BASE + "/health", timeout=1); break
        except Exception: time.sleep(0.5)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        page = ctx.new_page()
        page.goto(BASE + "/login")
        page.fill("#identifier", env["RLS_TEST_EMAIL_A"])
        page.fill("#password", env["RLS_TEST_PASSWORD_A"])
        page.click("button.submit-btn")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        # הכרטיס מופיע רק כשיש עסקאות — אחת היום ואחת בשבוע שעבר (החשבון זמני ונמחק בסוף)
        cats = page.request.get(BASE + "/api/categories").json()
        cat = next(c["id"] for c in cats if c["type"] == "expense")
        for days in (0, 8):
            page.request.fetch(BASE + "/api/transactions", method="POST", headers={"Content-Type": "application/json"},
                               data=json.dumps({"amount": 42, "type": "expense", "category_id": cat, "description": "WEEK-SWIPE",
                                                "date": (datetime.date.today() - datetime.timedelta(days=days)).isoformat()}))
        page.goto(BASE + "/")
        page.wait_for_timeout(1200)
        check("there is a week card", page.locator(".week-card").count() == 1)

        def gesture(xs, gap=8, hold=0):
            page.evaluate(GESTURE, [xs, gap, hold])
            page.wait_for_timeout(1500)                 # הבקשה לשבוע אחר והחלפת הכרטיס
            return int(page.evaluate("document.querySelector('.week-card').dataset.offset"))

        # 1. אותו מרחק קצר, לאט ועם עצירה — נשאר בשבוע הזה
        check("short slow drag stays on this week", gesture([-6, -12, -18, -24, -30], gap=60, hold=200) == 0)
        # 2. הנפה קצרה ומהירה שמאלה — לשבוע הקודם
        check("short fast flick goes to last week", gesture([-10, -20, -30]) == 1)
        # 3. הנפה קצרה ומהירה ימינה — חזרה לשבוע הזה
        check("short fast flick back returns to this week", gesture([10, 20, 30]) == 0)
        # 4. גרירה ארוכה ואיטית עם עצירה — מרחק לבדו עדיין עובד
        check("long slow drag still works", gesture([-15, -30, -45, -60, -75, -90], gap=40, hold=200) == 1)
        # 5. גרירה ארוכה שמאלה והנפה חזרה — לא עובר (הכיוון של לאן היא הולכת)
        check("long drag then flick back stays", gesture([-20, -40, -60, -80, -80, -80, -60, -40, -20], gap=12) == 1)
        # 6. אין שבוע הבא — הנפה ימינה מהשבוע הזה לא עושה כלום
        gesture([10, 20, 30])
        check("no next week from this week", gesture([10, 20, 30, 40]) == 0)
        b.close()
finally:
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)

print("\n%d failed" % len(failed))
sys.exit(1 if failed else 0)
