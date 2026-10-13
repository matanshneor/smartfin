// רישום ה-Service Worker והצעת ההתקנה למסך הבית.
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js')
            .catch(function () {});
    });
}

// ── "הוסיפו למסך הבית" (מתן, 13.10) ──
//
// פס קבוע מעל התפריט התחתון, עד שנכנסים פעם אחת מהאייקון. אז השרת זוכר
// (‎/api/app-installed‎ → ‎data-installed‎) — והפס לא חוזר גם בכניסה מהדפדפן.
// ✕ מסתיר עד הכניסה הבאה (‎sessionStorage‎). עד אז הייתה הודעה צהובה שנסגרה
// לתמיד בנגיעה אחת, וטקסט בלי הדרכה.
//
// באייפון אין התקנה בלחיצה — "איך?" פותח שלושה צעדים, בלי שם של דפדפן: מי
// שנכנס מכרום או מפיירפוקס גם מוסיף מכפתור השיתוף. מתוך וואטסאפ, אינסטגרם
// או פייסבוק אי אפשר בכלל — שם הצעד הראשון הוא לפתוח בדפדפן. באנדרואיד
// "התקנה" פותח את חלון ההתקנה של הטלפון; בלעדיו — שלושה צעדים מהתפריט.
(function () {
    const bar = typeof document.getElementById === 'function' && document.getElementById('installBar');
    if (!bar) return;
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
    if (isStandalone) {
        // נכנסו מהאייקון — פעם בכניסה מספיק; השרת מתעלם מכפילויות
        let told = false;
        try { told = sessionStorage.getItem('sf_app_marked') === '1'; } catch (e) { /* אין אחסון */ }
        if (!told && !bar.hasAttribute('data-installed')) {
            fetch('/api/app-installed', { method: 'POST', credentials: 'same-origin',
                                          headers: { 'Accept': 'application/json' } })
                .then(function (r) { if (r.ok) try { sessionStorage.setItem('sf_app_marked', '1'); } catch (e) { /* */ } })
                .catch(function () { /* בפעם הבאה */ });
        }
        return;
    }
    if (bar.hasAttribute('data-installed')) return;
    try { if (sessionStorage.getItem('sf_install_hidden') === '1') return; } catch (e) { /* מציגים */ }

    const ua = window.navigator.userAgent;
    const isIOS = /iphone|ipad|ipod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    const inApp = /FBAN|FBAV|Instagram|Line\/|LinkedInApp|TikTok|Snapchat|WhatsApp/i.test(ua);
    const go = document.getElementById('installBarGo');
    let deferredPrompt = null;

    function show() {
        bar.hidden = false;
        document.body.classList.add('has-install-bar');
    }
    function hide() {
        bar.hidden = true;
        document.body.classList.remove('has-install-bar');
    }
    document.getElementById('installBarClose').addEventListener('click', function () {
        hide();
        try { sessionStorage.setItem('sf_install_hidden', '1'); } catch (e) { /* יחזור בעמוד הבא */ }
    });

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;
        document.getElementById('installBarTitle').textContent = 'התקינו את SmartFin';
        document.getElementById('installBarSub').textContent = 'אייקון במסך הבית, כמו אפליקציה';
        go.textContent = 'התקנה';
    });
    window.addEventListener('appinstalled', hide);

    const SHARE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 10H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-2"/><path d="M12 15V3M8 7l4-4 4 4"/></svg>';
    const PLUS  = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8v8M8 12h8"/></svg>';
    const DOTS  = '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>';
    const ICON  = '<img src="/static/icons/icon-180.png" alt="">';

    function steps() {
        if (inApp) return [
            [DOTS, 'פתחו את הקישור <b>בדפדפן</b>', 'מהתפריט של האפליקציה שבה אתם נמצאים — "פתיחה בדפדפן"'],
            [isIOS ? SHARE : DOTS, isIOS ? 'שם — <b>שיתוף</b>, ואז <b>הוסף למסך הבית</b>' : 'שם — התפריט, ואז <b>הוסף למסך הבית</b>', ''],
            [ICON, 'ופתחו את SmartFin <b>מהאייקון</b>', ''],
        ];
        if (isIOS) return [
            [SHARE, 'הקישו על כפתור <b>השיתוף</b> של הדפדפן', 'הריבוע עם החץ למעלה'],
            [PLUS, 'בחרו <b>הוסף למסך הבית</b>', 'לא רואים? גללו למטה, או תחת "עוד"'],
            [ICON, 'הקישו <b>"הוסף"</b> — ופתחו את SmartFin מהאייקון', ''],
        ];
        return [
            [DOTS, 'פתחו את <b>התפריט</b> של הדפדפן', 'שלוש הנקודות'],
            [PLUS, 'בחרו <b>הוסף למסך הבית</b> או <b>התקנת אפליקציה</b>', ''],
            [ICON, 'אשרו — ופתחו את SmartFin מהאייקון', ''],
        ];
    }
    function guide() {
        const sheet = document.createElement('div');
        sheet.className = 'color-sheet install-guide';
        sheet.setAttribute('role', 'dialog');
        sheet.setAttribute('aria-modal', 'true');
        sheet.setAttribute('aria-label', 'הוספה למסך הבית');
        let html = '<div class="color-sheet-card"><p class="color-sheet-title">הוספה למסך הבית</p>'
                 + '<p class="color-sheet-hint">שלושה צעדים, פעם אחת — ומאז SmartFin נפתחת מהאייקון</p><ol class="install-steps">';
        steps().forEach(function (s, k) {
            html += '<li><span class="install-step-num">' + (k + 1) + '</span><span class="install-step-text">' + s[1]
                  + (s[2] ? '<span class="install-step-hint">' + s[2] + '</span>' : '')
                  + '</span><span class="install-step-pic">' + s[0] + '</span></li>';
        });
        html += '</ol><button type="button" class="btn-sm btn-ghost color-sheet-close">הבנתי</button></div>';
        sheet.innerHTML = html;      // טקסט קבוע מהקובץ הזה בלבד — אין כאן קלט של משתמש
        document.body.appendChild(sheet);
        bar.hidden = true;                      // הפס לא מעל ההדרכה
        function close() { sheet.remove(); bar.hidden = false; go.focus({ preventScroll: true }); }
        sheet.addEventListener('click', function (e) {
            if (e.target === sheet || e.target.closest('.color-sheet-close')) close();
        });
        document.addEventListener('keydown', function esc(e) {
            if (e.key === 'Escape') { document.removeEventListener('keydown', esc); close(); }
        });
        requestAnimationFrame(function () { sheet.querySelector('.color-sheet-close').focus(); });
    }
    go.addEventListener('click', function () {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.finally(function () { deferredPrompt = null; });
            return;
        }
        guide();
    });
    show();
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