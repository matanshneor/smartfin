"""בדיקת דפדפן אמיתי: מסך החיפוש ומסך "כל עסקאות החודש" עולים מלמטה ויורדים באותו מסלול (מתן, 7.10 — סבב תנועה, סעיף 3).

הרצה (Playwright מותקן בפייתון של המערכת, לא ב-.venv):
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 tests/browser/full_screens_motion.py

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

# לוחץ על ‎trigger‎ (או מקש), ומאותו רגע מודד בכל פריים את המסך עצמו
TRACK = """([trigger, key, screen, ms]) => new Promise(done => {
    const out = [];
    if (trigger) document.querySelector(trigger).click();
    if (key) document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    const t0 = performance.now();
    (function f() {
        const s = document.querySelector(screen);
        const cs = getComputedStyle(s), shown = cs.display !== 'none';
        out.push({ shown, y: shown ? new DOMMatrix(cs.transform === 'none' ? undefined : cs.transform).m42 : null,
                   o: shown ? parseFloat(cs.opacity) : null, tf: cs.transform, pe: cs.pointerEvents, hidden: s.hidden });
        if (performance.now() - t0 < ms) requestAnimationFrame(f); else done(out);
    })();
})"""

def opening(name, frames):
    ys = [f["y"] for f in frames if f["y"] is not None]
    check(f"{name}: rises into place ({len([y for y in ys if 1 < y < 24])} frames on the way)",
          len([y for y in ys if 1 < y < 24]) >= 3)
    check(f"{name}: …fading in (first opacity {frames[0]['o']})", frames[0]["o"] is not None and frames[0]["o"] < 0.5)
    check(f"{name}: …and at rest has no transform at all ({frames[-1]['tf']})", frames[-1]["tf"] == "none")

def closing(name, frames):
    ys = [f["y"] for f in frames if f["y"] is not None]
    check(f"{name}: slides back down on close ({len([y for y in ys if y > 1])} frames)", len([y for y in ys if y > 1]) >= 3)
    check(f"{name}: …doesn't block taps on the way out",
          # מהרגע שהסגירה התחילה — ב"כל העסקאות" Escape עובר דרך ‎history.back()‎
          all(f["pe"] == "none" for f in frames if f["shown"] and f["hidden"]))
    check(f"{name}: …and is really gone in the end", not frames[-1]["shown"])

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
        # "לכל עסקאות החודש" מופיע רק כשיש בחודש יותר מ-5 עסקאות
        cat = next(c["id"] for c in page.request.get(BASE + "/api/categories").json() if c["type"] == "expense")
        for i in range(7):
            page.request.fetch(BASE + "/api/transactions", method="POST", headers={"Content-Type": "application/json"},
                data=json.dumps({"amount": 10 + i, "type": "expense", "category_id": cat, "description": "SCREEN-MOTION",
                                 "date": datetime.date.today().isoformat()}))

        page.goto(BASE + "/"); page.wait_for_timeout(1500)
        opening("search", page.evaluate(TRACK, ["#searchOpen", None, ".search-screen", 600]))
        page.wait_for_timeout(200)
        closing("search", page.evaluate(TRACK, [None, "Escape", ".search-screen", 500]))

        page.goto(BASE + "/month"); page.wait_for_timeout(1500)
        check("the month has the all-transactions button", page.locator("#txScreenOpen").count() == 1)
        opening("all transactions", page.evaluate(TRACK, ["#txScreenOpen", None, "#txScreen", 600]))
        page.wait_for_timeout(200)
        closing("all transactions", page.evaluate(TRACK, [None, "Escape", "#txScreen", 500]))
        b.close()
finally:
    os.killpg(os.getpgid(srv.pid), signal.SIGTERM)
    time.sleep(2)

print("\n%d failed" % len(failed))
sys.exit(1 if failed else 0)
