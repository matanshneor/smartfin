"""בדיקת דפדפן אמיתי: כפתורי הסרגל, החלונות והבחירה הוצאה/הכנסה מתכווצים ברגע הלחיצה (מתן, 7.10 — סבב תנועה, סעיף 6).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/press_feedback.py

מדפיס PASS/FAIL לכל מקרה ויוצא עם קוד 1 אם משהו נכשל.
"""
import os, sys, time, subprocess, signal
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

def scale(page, sel):
    return page.evaluate("""s => { const t = getComputedStyle(document.querySelector(s)).transform;
        return t === 'none' ? 1 : new DOMMatrix(t).a; }""", sel)

def press(page, target, measure, want):
    box = page.locator(target).first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down(); page.wait_for_timeout(250)
    held = scale(page, measure)
    # עוזבים מחוץ לכפתור — בלי ללחוץ באמת (לא לנווט, לא לסגור)
    page.mouse.move(5, 5); page.mouse.up(); page.wait_for_timeout(250)
    after = scale(page, measure)
    check(f"{target}: shrinks while pressed (scale {held:.2f}, want {want})", abs(held - want) < 0.005)
    check(f"{target}: …and comes back on release (scale {after:.2f})", abs(after - 1) < 0.005)

try:
    for _ in range(40):
        try:
            import urllib.request; urllib.request.urlopen(BASE + "/health", timeout=1); break
        except Exception: time.sleep(0.5)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 390, "height": 844})
        page.goto(BASE + "/login")
        page.fill("#identifier", env["RLS_TEST_EMAIL_A"])
        page.fill("#password", env["RLS_TEST_PASSWORD_A"])
        page.click("button.submit-btn")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        page.goto(BASE + "/"); page.wait_for_timeout(1200)

        page.evaluate("document.querySelectorAll('.nav-item')[1].id = 'pressNav'")
        press(page, "#pressNav", "#pressNav .nav-icon", 0.94)

        page.click("#fabBtn"); page.wait_for_timeout(700)
        page.evaluate("document.activeElement.blur()")
        page.evaluate("document.querySelectorAll('#modalOverlay .toggle-btn')[1].id = 'pressToggle'")
        press(page, "#pressToggle", "#pressToggle", 0.97)
        # עזיבה מחוץ לחלון נחשבת לחיצה על הרקע וסוגרת אותו — ואם לא, ‎Escape‎
        if page.locator("#modalOverlay.open").count(): page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # חלון אישור — דרך ‎appConfirm‎ עצמו, בלי למחוק כלום
        # בלי ‎return‎: ‎appConfirm‎ מחזיר הבטחה שמחכה לתשובה, ו-‎evaluate‎ היה מחכה איתה לנצח
        page.evaluate("() => { window.appConfirm({ title: 'בדיקה', message: 'בדיקה', confirmText: 'כן' }); }")
        page.wait_for_timeout(400)
        press(page, "#confirmNo", "#confirmNo", 0.97)
        # כפתור מושבת — לא נבדק כאן: הדפדפן עצמו לא מסמן אותו ‎:active‎, אז בדיקה
        # כזו עוברת גם בלי ‎:not(:disabled)‎ ולא שומרת על כלום
        b.close()
finally:
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)

print("\n%d failed" % len(failed))
sys.exit(1 if failed else 0)
