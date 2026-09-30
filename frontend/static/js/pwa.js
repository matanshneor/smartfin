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
