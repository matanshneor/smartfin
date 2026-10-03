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
(function () {
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
    if (!isStandalone || !('ontouchstart' in window)) return;

    const START = 8;        // עד כאן זו עוד לא גרירה
    const TRIGGER = 70;     // משיכה מעבר לזה מרעננת בשחרור
    const MAX = 110;

    const ind = document.createElement('div');
    ind.className = 'ptr';
    ind.setAttribute('aria-hidden', 'true');
    const SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        + ' stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">';
    const ARROW = SVG + '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>';
    const SPIN  = SVG + '<path d="M21 12a9 9 0 1 1-6.2-8.55"/></svg>';
    ind.innerHTML = ARROW;
    document.body.appendChild(ind);

    let startX = 0, startY = null, pulling = false, pull = 0, busy = false;

    function show(dist) {
        pull = dist;
        ind.style.transform = 'translate(-50%, ' + (dist - 50) + 'px)';
        ind.style.opacity = Math.min(1, dist / TRIGGER);
        ind.classList.toggle('ready', dist >= TRIGGER);
    }
    function reset() {
        startY = null; pulling = false;
        ind.classList.remove('ready', 'spinning');
        ind.innerHTML = ARROW;
        ind.style.transition = 'transform .2s, opacity .2s';
        show(0);
        setTimeout(function () { ind.style.transition = ''; }, 220);
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
        if (window.scrollY > 0) { reset(); return; }
        e.preventDefault();
        show(Math.min(MAX, (dy - START) * 0.55));
    }, { passive: false });

    document.addEventListener('touchend', function () {
        if (!pulling) { startY = null; return; }
        if (pull < TRIGGER) { reset(); return; }
        busy = true;
        ind.classList.add('spinning');
        ind.innerHTML = SPIN;
        show(TRIGGER);
        // עמוד שבטוח להחלפה — רענון רך, בלי הבהוב; כל השאר — רענון מלא
        const soft = document.querySelector('main[data-soft-reload]') && window.softReload;
        if (!soft) { window.location.reload(); return; }
        Promise.resolve(window.softReload()).then(function () {
            busy = false; reset();
        }, function () {
            busy = false; reset();
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