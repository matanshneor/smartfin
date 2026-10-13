// רישום ה-Service Worker והצעת ההתקנה למסך הבית.
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js')
            .catch(function () {});
    });
}

(function () {
    const DISMISS_KEY = 'sf_install_dismissed';
    // ‎try/catch‎: זו הגישה האחרונה בריפו ל-‎localStorage‎ שלא הייתה
    // מוגנת. ב-Safari עם עוגיות חסומות, בגלישה פרטית או ב-Lockdown
    // Mode הקריאה **זורקת** — וכאן, בשורה הראשונה של ה-IIFE, היא
    // הורגת את כל הקובץ. אותה נפילה בדיוק שקרתה ל-core.js.
    try {
        if (localStorage.getItem(DISMISS_KEY)) return;
    } catch (e) { /* אין אחסון — מציגים את ההצעה, במקום לא כלום */ }

    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
    if (isStandalone) return;

    const banner  = document.getElementById('installBanner');
    const text    = document.getElementById('installBannerText');
    const actionBtn = document.getElementById('installBannerAction');
    const closeBtn  = document.getElementById('installBannerClose');
    let deferredPrompt = null;

    function dismiss() {
        banner.style.display = 'none';
        try {
            localStorage.setItem(DISMISS_KEY, '1');
        } catch (e) { /* לא נזכר — הבאנר יחזור, וזה עדיף על קריסה */ }
    }
    closeBtn.addEventListener('click', dismiss);

    const isIOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;
        text.textContent = 'התקינו את SmartFin למסך הבית לגישה מהירה יותר';
        actionBtn.style.display = '';
        banner.style.display = '';
    });

    actionBtn.addEventListener('click', function () {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.finally(dismiss);
    });

    window.addEventListener('appinstalled', dismiss);

    // ל-iOS אין beforeinstallprompt בכלל — מציגים הנחיה סטטית בלבד
    if (isIOS) {
        text.textContent = 'להתקנת SmartFin: הקישו על שיתוף ← הוסף למסך הבית';
        banner.style.display = '';
    }
})();


// ── משיכה למטה לרענון — רק באפליקציה המותקנת (מתן, 30.9 — רעיון 14) ──
//
// ב-Safari רגיל זה קיים מעצמו. באפליקציה שנפתחת ממסך הבית אין שורת כתובת
// ואין משיכה, ואין שום דרך לרענן — מי שחיכה לעסקה שבן הזוג הזין נאלץ
// לסגור ולפתוח. מתחילים רק בראש העמוד, רק בגרירה אנכית (החלקה הצידה על
// שורה היא עריכה/מחיקה), ולא כשחלון או עורך פתוחים.
//
// כמו באייפון (מתן, 13.10): העמוד עצמו יורד עם האצבע, בהתנגדות של קפיץ
// (כמה שמושכים יותר — זז פחות), ובפס הכהה שנחשף מעליו — גלגל הטעינה של
// iOS, שהשפיצים שלו מופיעים אחד-אחד עם המשיכה. בשחרור מעבר לסף העמוד נעצר
// מעט למטה והגלגל מסתובב עד שהרענון נגמר; ואז הכול חוזר למעלה בקפיצה רכה.
(function () {
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
    if (!isStandalone || !('ontouchstart' in window)) return;

    const START = 8;        // עד כאן זו עוד לא גרירה
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // הפס העליון של המסך מתחת לשעון ולסוללה — הגלגל מופיע מתחתיו
    const probe = document.createElement('div');
    probe.style.cssText = 'position:fixed;top:0;height:env(safe-area-inset-top,0px);visibility:hidden;pointer-events:none';
    document.body.appendChild(probe);
    const SAFE = probe.getBoundingClientRect().height || 0;
    probe.remove();
    const TRIGGER = SAFE + 58;    // משיכה מעבר לזה מרעננת בשחרור
    const HOLD = SAFE + 50;       // כאן העמוד מחכה בזמן הרענון
    const RANGE = 320;            // הקפיץ: ככל שמתקרבים לזה — זז פחות

    const layer = document.createElement('div');
    layer.className = 'ptr-layer';
    layer.setAttribute('aria-hidden', 'true');
    let spokes = '';
    for (let k = 0; k < 8; k++) {
        spokes += '<line x1="12" y1="2.5" x2="12" y2="7" transform="rotate(' + (k * 45) + ' 12 12)"'
                + ' style="opacity:' + (1 - k * 0.11).toFixed(2) + '"/>';
    }
    layer.innerHTML = '<svg class="ptr-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
                    + ' stroke-width="2.4" stroke-linecap="round">' + spokes + '</svg>';
    document.body.appendChild(layer);
    const spinner = layer.firstChild;
    const lines = spinner.querySelectorAll('line');

    // מה זז: הכותרת הכהה והתוכן (‎body > .page-hero, body > .main-content‎ —
    // ב-CSS, לפי משתנה על ‎body‎). לא ‎style‎ על האלמנטים עצמם: הרענון הרך
    // מחליף אותם באמצע, והעמוד היה קופץ למעלה לפני שהגלגל סיים. התפריט התחתון
    // וכפתור ה-+ נשארים במקום.
    const root = document.body;

    let startX = 0, startY = null, pulling = false, pull = 0, busy = false;

    function place(dist, animate) {
        pull = dist;
        const t = animate ? (calm ? 'transform .15s ease' : 'transform .45s cubic-bezier(.2, 1.1, .3, 1)') : 'none';
        root.classList.add('ptr-active');
        root.style.setProperty('--ptr-t', t);
        root.style.setProperty('--ptr-y', dist + 'px');
        layer.style.transition = animate ? t.replace('transform', 'height') : 'none';
        layer.style.height = dist + 'px';
        // הגלגל באמצע החלק הנראה של הפס, מתחת לשעון
        const visible = Math.max(0, dist - SAFE);
        spinner.style.top = (SAFE + Math.max(0, visible / 2 - 12)) + 'px';
        spinner.style.opacity = Math.min(1, visible / 28);
    }
    function progress(dist) {
        // השפיצים מופיעים אחד-אחד עד הסף — כמו באייפון
        const n = busy ? 8 : Math.max(0, Math.min(8, Math.round((dist - SAFE) / (TRIGGER - SAFE) * 8)));
        lines.forEach(function (l, k) { l.style.visibility = k < n ? 'visible' : 'hidden'; });
    }
    function springBack() {
        startY = null; pulling = false;
        layer.classList.remove('spinning');
        place(0, true);
        setTimeout(function () {
            if (busy || pulling) return;
            // בלי ‎transform‎ בכלל במנוחה — אחרת חלונות ‎fixed‎ בתוך העמוד נכלאים בו
            root.classList.remove('ptr-active');
            layer.style.height = '0px';
        }, 480);
    }
    // חלון פתוח — חיפוש, תקציבים, אייקונים, צבעים, אישור. בתוכו גרירה למטה
    // היא גלילה של הרשימה שלו; קודם היא נתפסה כמשיכה, הרשימה לא זזה למעלה
    // והעמוד שמאחור התרענן.
    const OPEN_WINDOWS = '.modal-overlay.open, .transaction-item.open, .confirm-overlay.open, '
                       + '.search-screen:not([hidden]), .icon-picker:not([hidden]), .color-sheet:not([hidden])';
    function blocked(target) {
        return busy || window.scrollY > 0
            || document.querySelector(OPEN_WINDOWS)
            || (target.closest && target.closest('input, textarea, select, canvas, .tx-cat-chips, [role="dialog"]'));
    }

    document.addEventListener('touchstart', function (e) {
        if (e.touches.length !== 1 || blocked(e.target)) { startY = null; return; }
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        pulling = false;
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
        if (startY === null) return;
        const dx = e.touches[0].clientX - startX;
        const dy = e.touches[0].clientY - startY;
        if (!pulling) {
            // גלילה למעלה או תנועה הצידה — זה לא בשבילנו
            if (dy < 0 || Math.abs(dx) > Math.abs(dy)) {
                if (Math.abs(dx) > START || dy < -START) startY = null;
                return;
            }
            if (dy < START) return;
            pulling = true;
        }
        if (window.scrollY > 0) { springBack(); return; }
        e.preventDefault();
        const x = Math.max(0, dy - START);
        const dist = (1 - 1 / (x * 0.55 / RANGE + 1)) * RANGE;     // קפיץ
        place(dist, false);
        progress(dist);
    }, { passive: false });

    document.addEventListener('touchend', function () {
        if (!pulling) { startY = null; return; }
        if (pull < TRIGGER) { springBack(); return; }
        busy = true;
        pulling = false;
        progress(HOLD);
        layer.classList.add('spinning');
        place(HOLD, true);
        // עמוד שבטוח להחלפה — רענון רך, בלי הבהוב; כל השאר — רענון מלא
        const soft = document.querySelector('main[data-soft-reload]') && window.softReload;
        if (!soft) { setTimeout(function () { window.location.reload(); }, 250); return; }
        const shown = new Promise(function (r) { setTimeout(r, 500); });   // שיספיקו לראות שהסתובב
        Promise.all([Promise.resolve(window.softReload()).catch(function () {}), shown]).then(function () {
            busy = false; springBack();
        });
    });
})();


// ── התפריט התחתון נשאר למטה — רק באפליקציה המותקנת באייפון (מתן, 1.10) ──
//
// באג ידוע של iOS באפליקציה ממסך הבית: אלמנטים ‎position: fixed‎ "נסחפים"
// בגלילה ונתקעים באמצע המסך עד מעבר עמוד (מתן: "סתם בגלילה", "נשאר תקוע").
// מעבר עמוד מתקן — כי הוא מחשב אותם מחדש. אז כשהגלילה נעצרת מחשבים אותם
// מחדש בעצמנו, ואם המסך הנראה והמסך שהדפדפן מחשב לא נגמרים באותו מקום —
// מזיזים אותם לתחתית האמיתית. בזמן הקלדה לא נוגעים: המקלדת מקצרת את המסך
// הנראה בכוונה, והתפריט לא אמור לטפס מעליה.
(function () {
    if (window.navigator.standalone !== true) return;
    const vv = window.visualViewport;

    window.sfDockOffset = function (innerHeight, vvHeight, vvOffsetTop) {
        const gap = Math.round(innerHeight - (vvHeight + vvOffsetTop));
        return Math.abs(gap) > 2 ? -gap : 0;
    };

    function typing() {
        const a = document.activeElement;
        return a && a.matches && a.matches('input, textarea, select, [contenteditable="true"]');
    }

    function settle() {
        const shift = (vv && !typing())
            ? window.sfDockOffset(window.innerHeight, vv.height, vv.offsetTop) : 0;
        document.querySelectorAll('.bottom-nav, .fab').forEach(function (el) {
            // חישוב מחדש: יציאה רגעית מ-fixed וחזרה, בלי ציור באמצע
            el.style.position = 'absolute';
            void el.offsetHeight;
            el.style.position = '';
            // ‎translate‎ ולא ‎transform‎ — לא דורס את הלחיצה (‎scale‎) של כפתור ה-+
            el.style.translate = shift ? '0 ' + shift + 'px' : '';
        });
    }

    let timer = null;
    function soon() { clearTimeout(timer); timer = setTimeout(settle, 120); }
    window.addEventListener('scroll', soon, { passive: true });
    if (vv) { vv.addEventListener('resize', soon); vv.addEventListener('scroll', soon); }
    window.addEventListener('pageshow', soon);
    window.addEventListener('sf:refreshed', soon);
    document.addEventListener('focusout', soon);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) soon(); });
})();



// ── טעינה מוקדמת בנגיעה בקישור (מתן, 3.10 — רעיון 29) ──
// ‎pointerdown‎ — נגיעה בטלפון, לחיצה בעכבר. ראו ‎sw.js‎: העמוד מתחיל להיטען
// כבר עכשיו, והניווט שמגיע כשהאצבע עוזבת מקבל אותו.
(function () {
    if (!('serviceWorker' in navigator)) return;
    document.addEventListener('pointerdown', function (e) {
        const sw = navigator.serviceWorker.controller;
        if (!sw) return;
        const a = e.target.closest && e.target.closest('a[href]');
        if (!a || a.target || a.hasAttribute('download')) return;
        let url;
        try { url = new URL(a.href, location.href); } catch (err) { return; }
        if (url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
        // אותו עמוד (או רק עוגן בתוכו) — אין מה לטעון
        if (url.pathname === location.pathname && url.search === location.search) return;
        sw.postMessage({ type: 'prefetch', url: url.pathname + url.search });
    }, { passive: true, capture: true });
})();