"""בדיקת דפדפן אמיתי: החלקה על שורת עסקה לפי מהירות האצבע (מתן, 7.10 — עיצוב בנוסח אפל, סעיף 2).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/row_swipe.py

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

# מחווה שלמה מתוך הדף: תנועה כל ‎gap‎ ms (8 — מסך אמיתי; דרך CDP כל תנועה
# מתעכבת ~40ms). ‎xs‎ — היסטים אופקיים מנקודת ההתחלה; ‎ys‎ — אנכיים, אם יש.
# מחזיר את מיקום השורה רגע לפני העזיבה, כפי שהוא באמת מצויר.
GESTURE = """([sel, xs, ys, gap, hold]) => new Promise(done => {
    const row = document.querySelector(sel);
    const r = row.getBoundingClientRect();
    const x0 = r.left + r.width / 2, y0 = r.top + r.height / 2;
    const el = document.elementFromPoint(x0, y0);
    const at = (dx, dy) => new Touch({ identifier: 1, target: el, clientX: x0 + dx, clientY: y0 + dy });
    let last = at(0, 0);
    const fire = (type, t) => el.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true,
        touches: t ? [t] : [], targetTouches: t ? [t] : [], changedTouches: [t || last] }));
    fire('touchstart', last);
    let i = 0;
    const tick = () => {
        if (i < xs.length) { last = at(xs[i], ys ? ys[i] : 0); fire('touchmove', last); i++; setTimeout(tick, gap); return; }
        setTimeout(() => {
            const c = row.querySelector('.swipe-content');
            const mid = c ? new DOMMatrix(getComputedStyle(c).transform).m41 : 0;
            fire('touchend', null);
            done(mid);
        }, hold);
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
        cats = page.request.get(BASE + "/api/categories").json()
        cat = next(c["id"] for c in cats if c["type"] == "expense")
        page.request.fetch(BASE + "/api/transactions", method="POST", headers={"Content-Type": "application/json"},
                           data=json.dumps({"amount": 42, "type": "expense", "category_id": cat,
                                            "date": datetime.date.today().isoformat(), "description": "SWIPE-TEST"}))
        page.goto(BASE + "/")
        page.wait_for_timeout(1200)
        SEL = ".transaction-item[data-id]"
        check("there is a row to swipe", page.locator(SEL).count() > 0)

        def gesture(xs, gap=8, hold=0, ys=None):
            return page.evaluate(GESTURE, [SEL, xs, ys, gap, hold])

        def state():
            return page.evaluate("""(sel) => { const r = document.querySelector(sel), c = r.querySelector('.swipe-content');
                return { open: r.classList.contains('swipe-open'),
                         x: c ? new DOMMatrix(getComputedStyle(c).transform).m41 : 0 }; }""", SEL)

        def reset():
            page.evaluate("""(sel) => { const r = document.querySelector(sel), c = r.querySelector('.swipe-content');
                r.classList.remove('swipe-open');
                // בלי מעבר רק לרגע — ואז ה-CSS חוזר, כדי שמקרה 4 יראה השהיה אם יש כזו
                if (c) { c.style.transition = 'none'; c.style.transform = ''; void c.offsetWidth; c.style.transition = ''; } }""", SEL)
            page.wait_for_timeout(100)

        # 1. הנפה קצרה ומהירה שמאלה (36px) — נפתחת, ונעצרת ברוחב הכפתור
        gesture([-12, -24, -36])
        page.wait_for_timeout(900)
        s = state()
        check("short fast flick opens the row (open=%s, x=%.0f)" % (s["open"], s["x"]), s["open"] and abs(s["x"] + 76) < 2)
        reset()

        # 2. אותו מרחק, לאט ועם עצירה — נשאר סגור (ההחלטה לפי מהירות, לא רק מרחק)
        gesture([-6, -12, -18, -24, -30, -36], gap=60, hold=200)
        page.wait_for_timeout(900)
        s = state()
        check("same distance, slow and stopped, stays closed (open=%s, x=%.0f)" % (s["open"], s["x"]),
              not s["open"] and abs(s["x"]) < 1)
        reset()

        # 3. גרירה ארוכה ואיטית ימינה עם עצירה — נפתחת (מרחק לבדו עדיין עובד)
        gesture([10, 20, 30, 40, 50, 60, 70], gap=40, hold=200)
        page.wait_for_timeout(900)
        s = state()
        check("long slow drag right opens (open=%s, x=%.0f)" % (s["open"], s["x"]), s["open"] and abs(s["x"] - 76) < 2)
        reset()

        # 4. השורה זזה עם האצבע אחד לאחד, בלי השהיה (50px → 42, אחרי 8 של ההחלטה)
        mid = gesture([-10, -20, -30, -40, -50], gap=16, hold=0)
        check("row follows the finger with no lag (got %.0f, want -42)" % mid, abs(mid + 42) < 2)
        page.wait_for_timeout(900)
        reset()

        # 5. מעבר לרוחב הכפתור — התנגדות הדרגתית, לא קיר
        mid = gesture([-40, -80, -120, -160, -200], gap=16, hold=0)
        # בלי התנגדות: ‎-192‎; הקיר הישן: ‎-100‎
        check("past the button it resists, no hard stop (got %.0f)" % mid, -160 < mid < -110)
        page.wait_for_timeout(900)
        reset()

        # 6. הנפה חזרה אחרי גרירה ארוכה — נסגרת (הכיוון של לאן היא הולכת)
        gesture([-15, -30, -45, -60, -70, -70, -70, -60, -45, -30], gap=12)
        page.wait_for_timeout(900)
        s = state()
        check("flick back after a long drag closes (open=%s, x=%.0f)" % (s["open"], s["x"]), not s["open"] and abs(s["x"]) < 1)
        reset()

        # 6ב. התחרטות חזקה: שמאלה, ואז הנפה מהירה ימינה — נסגרת, לא נפתחת "עריכה" מהצד השני
        gesture([-15, -30, -45, -60, -70, -70, -50, -30, -15], gap=8)
        page.wait_for_timeout(900)
        s = state()
        check("drag left then hard flick right doesn't open the other side (open=%s, x=%.0f)" % (s["open"], s["x"]),
              not s["open"] and abs(s["x"]) < 1)
        reset()

        # 7. גלילה אנכית — השורה לא זזה
        gesture([2, 4, 6, 8], ys=[-20, -40, -60, -80])
        page.wait_for_timeout(600)
        s = state()
        check("vertical scroll doesn't swipe (x=%.0f)" % s["x"], not s["open"] and abs(s["x"]) < 1)

        # 8. נגיעה בשורה פתוחה סוגרת אותה (כמו קודם)
        gesture([-12, -24, -36])
        page.wait_for_timeout(900)
        gesture([], hold=30)
        page.wait_for_timeout(600)
        s = state()
        check("a tap on an open row closes it (open=%s, x=%.0f)" % (s["open"], s["x"]), not s["open"] and abs(s["x"]) < 1)
        b.close()
finally:
    cleanup = "\n".join([
        "import os, sys", "sys.path.insert(0, '.')",
        "from dotenv import load_dotenv; load_dotenv('.env')",
        "from backend import supabase_config as db",
        "r, _ = db.sign_in(os.environ['RLS_TEST_EMAIL_A'], os.environ['RLS_TEST_PASSWORD_A'])",
        "db.set_auth_token(r.session.access_token)",
        "fid = db.get_profile(r.user.id)['family_id']",
        "db.get_client().table('transactions').delete().eq('family_id', fid).eq('description', 'SWIPE-TEST').execute()",
    ])
    subprocess.run([os.path.join(ROOT, ".venv/bin/python3"), "-c", cleanup], cwd=ROOT)
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)

print("\n%d failed" % len(failed))
sys.exit(1 if failed else 0)
