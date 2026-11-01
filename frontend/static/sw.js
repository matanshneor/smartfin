const CACHE = 'smartfin-v23';

// אין טעינה-מראש.
//
// הכתובות של הנכסים נושאות עכשיו חתימת תוכן (‎?v=…‎) שנקבעת בשרת, ורשימה
// קבועה כאן לא יכולה לדעת אותה — היא הייתה מורידה כתובות בלי חתימה שאף
// עמוד לא מבקש, כלומר הורדה כפולה של כל קובץ ומטמון שלא נוגעים בו לעולם.
//
// וזה ממילא לא נחוץ יותר: כתובת חתומה מוגשת עם תוקף של שנה, אז הדפדפן
// שומר אותה בעצמו כבר מהביקור הראשון. מה שמגיע לכאן נשמר בזמן אמת למטה.
self.addEventListener('install', function () {
    self.skipWaiting();
});

self.addEventListener('activate', function (e) {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});


/* עמוד "אין חיבור". טוען את גיליון הסגנון מהמטמון — הוא כבר שם — כדי
 * שזה ייראה כמו האפליקציה ולא כמו שגיאת דפדפן. כפתור הניסיון החוזר קיים
 * כי בלעדיו הדרך היחידה קדימה היא רענון ידני, ובאפליקציה מותקנת בטלפון
 * אין כפתור רענון על המסך. */
function offlinePage() {
    return new Response(
        '<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">' +
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' +
        '<title>אין חיבור</title>' +
        // מצב כהה גם כאן (סקירה של 1.10). לתשובה שנבנית כאן אין CSP, אז שורה
        // בתוך העמוד מותרת — js/theme.js אולי לא במטמון כשאין רשת
        '<script>try{if(localStorage.getItem("sf_theme")==="dark")document.documentElement.setAttribute("data-theme","dark")}catch(e){}</script>' +
        '<link rel="stylesheet" href="/static/css/style.css"></head>' +
        '<body class="auth-body"><div class="auth-container">' +
        '<div class="empty-state">' +
        '<div class="empty-illus" aria-hidden="true"><svg class="ui-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M12 20h.01"/><path d="M8.5 16.43a5 5 0 0 1 7 0"/><path d="M2 8.82a15 15 0 0 1 4.18-2.65"/>' +
        '<path d="M19 12.86a10 10 0 0 0-1.86-1.42"/><path d="M22 8.82a15 15 0 0 0-11.29-3.76"/>' +
        '<path d="M5 12.86a10 10 0 0 1 5.17-2.69"/><path d="m2 2 20 20"/></svg></div>' +
        '<p class="empty-text">אין חיבור לאינטרנט</p>' +
        '<p class="empty-sub">המספרים שלכם מחכים ברגע שהחיבור יחזור. ' +
        'לא מוצגים כאן נתונים ישנים, כדי שלא תסתמכו על מספר שכבר לא נכון.</p>' +
        '<button class="submit-btn" onclick="location.reload()">נסו שוב</button>' +
        '</div></div></body></html>',
        { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
}

/* ── טעינה מוקדמת בנגיעה (מתן, 3.10 — רעיון 29) ──
 *
 * הדפדפן מבקש עמוד רק כשהאצבע עוזבת את המסך. כשהיא **נוגעת** בקישור,
 * העמוד שולח לכאן הודעה, ואנחנו מתחילים להביא אותו כבר אז. אם תוך כמה
 * שניות מגיע ניווט לאותה כתובת — הוא מקבל את התשובה הזאת במקום בקשה חדשה.
 *
 * בזיכרון בלבד, לכמה שניות, ותשובה אחת לניווט אחד: זה לא מטמון. מה שכתוב
 * למטה ("אף עמוד מאחורי ההתחברות לא מוגש מהמטמון") נשאר נכון — מה שמוגש
 * כאן הוא תשובה שנולדה רגע לפני שלחצו, לא עמוד מלפני ימים. */
const PREFETCH_TTL = 5000;
const prefetched = new Map();     // כתובת → { at, response: Promise<Response|null> }

self.addEventListener('message', function (e) {
    const data = e.data || {};
    if (data.type !== 'prefetch' || typeof data.url !== 'string') return;
    let url;
    try { url = new URL(data.url, self.location.origin); } catch (err) { return; }
    if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
    const key = url.pathname + url.search;
    const now = Date.now();
    for (const [k, v] of prefetched) if (now - v.at > PREFETCH_TTL) prefetched.delete(k);
    if (prefetched.has(key)) return;
    prefetched.set(key, {
        at: now,
        // רק תשובה תקינה של HTML, ובלי הפניה: Safari מסרב להגיש תשובה
        // שהופנתה (למשל להתחברות, כשהסשן פג) לניווט. אז הניווט ילך לרשת.
        response: fetch(url.href, { credentials: 'same-origin' })
            .then(res => (res.ok && !res.redirected &&
                          (res.headers.get('Content-Type') || '').includes('text/html')) ? res : null)
            .catch(() => null),
    });
});

function takePrefetched(request) {
    if (request.mode !== 'navigate') return null;
    const url = new URL(request.url);
    const key = url.pathname + url.search;
    const hit = prefetched.get(key);
    if (!hit) return null;
    prefetched.delete(key);                       // תשובה אחת לניווט אחד
    if (Date.now() - hit.at > PREFETCH_TTL) return null;
    return hit.response;
}

self.addEventListener('fetch', function (e) {
    // Only intercept same-origin GET requests
    if (e.request.method !== 'GET') {
        // שמירה/מחיקה/הוספה הופכת כל עמוד שנטען מוקדם לישן: נגיעה ב"ביטול"
        // ואז "שמירה" תוך 5 שניות החזירה לעמוד הפרויקט את המצב שלפני השמירה
        // (מתן, 9.10). הכתיבה עצמה עוברת לרשת כרגיל.
        prefetched.clear();
        return;
    }
    if (!e.request.url.startsWith(self.location.origin)) return;

    const url = new URL(e.request.url);

    // API calls: תמיד ישירות לרשת, בלי קאש ובלי נפילה-חזרה. נתוני עסקאות/
    // קטגוריות/פרויקטים משתנים כל הזמן — הגשה בשקט של תשובה ישנה מהקאש
    // בזמן כשל רשת הייתה גרועה יותר מהצגת שגיאת רשת אמיתית וברורה.
    if (url.pathname.startsWith('/api/')) {
        return;
    }

    // Static assets: stale-while-revalidate — מגיש מהמטמן מיד (מהיר), אבל
    // תמיד מושך גרסה טרייה ברקע ומעדכן את המטמן, כך ששינוי ב-CSS/JS מופיע
    // אוטומטית ברענון הבא בלי צורך בעדכון גרסת CACHE ידני בכל פעם.
    // רק תגובות תקינות נשמרות — לא שומרים 404/500 חולפים במטמון.
    if (url.pathname.startsWith('/static/')) {
        // כתובת חתומה (‎?v=…‎) היא בהגדרה בלתי משתנה: שינוי בקובץ מייצר
        // חתימה אחרת, כלומר כתובת אחרת. אז אם היא במטמון — זו התשובה,
        // בלי לבדוק ברשת. כתובת בלי חתימה (למשל קובץ שנטען ידנית) ממשיכה
        // לקבל את ההתנהגות הקודמת: מהמטמון מיד, ורענון ברקע.
        const immutable = url.searchParams.has('v');
        e.respondWith(
            caches.open(CACHE).then(cache =>
                cache.match(e.request).then(cached => {
                    if (cached && immutable) return cached;
                    const network = fetch(e.request).then(res => {
                        if (res.ok) cache.put(e.request, res.clone());
                        return res;
                    // בלי רשת ובלי עותק מדויק: כל גרסה שמורה של אותו קובץ
                    // עדיפה על כלום. מסך "אין חיבור" מבקש ‎style.css‎ בלי
                    // ‎?v=‎ — הוא לא יודע את החתימה — והמטמון מחזיק רק כתובות
                    // חתומות, אז המסך שנועד להיראות כמו האפליקציה הוצג כטקסט.
                    }).catch(() => cached || cache.match(e.request, { ignoreSearch: true }));
                    return cached || network;
                })
            )
        );
        return;
    }

    // ── מה נשמר במטמון, ומה לעולם לא ──
    //
    // כל עמוד מאחורי ההתחברות מציג כסף או פרטים אישיים, ולכן אף אחד מהם
    // לא מוגש מהמטמון. זה נראה כמו ויתור על אופליין וזה ההפך: משתמש
    // בחיבור סלולרי גרוע קיבל מסך מלא ומעוצב עם "נשאר בעו״ש ₪1,270"
    // מהביקור הקודם, אולי מלפני ימים. אנימציית הספירה אפילו רצה עליהם,
    // אז הם נראו טריים. שום דבר לא סימן שזה ישן — והוא עלול לקבל החלטה
    // כספית על סמך זה. הודעה ברורה שאין חיבור טובה ממספר שקרי.
    //
    // השורש וטופס ההתחברות מוחרגים מסיבה נוספת: התוכן שלהם נגזר מהעוגיות
    // (דף נחיתה לאורח, דשבורד למחובר, המייל השמור בטופס).
    //
    // רק העמודים המשפטיים נשמרים — הם זהים לכולם ולא משתנים.
    const CACHEABLE_PAGES = ['/privacy', '/terms'];

    if (!CACHEABLE_PAGES.includes(url.pathname)) {
        const early = takePrefetched(e.request);
        e.respondWith(
            (early || Promise.resolve(null))
                .then(res => res || fetch(e.request))
                .catch(() => offlinePage())
        );
        return;
    }

    // עמודים סטטיים: מהרשת קודם, ומהמטמון כשאין רשת
    e.respondWith(
        fetch(e.request)
            .then(res => {
                if (res.ok) {
                    const clone = res.clone();
                    caches.open(CACHE).then(c => c.put(e.request, clone));
                }
                return res;
            })
            .catch(() => caches.match(e.request).then(cached => cached || offlinePage()))
    );
});


/* ── התראות לטלפון (מתן, 31.10) ──
 * השרת שולח ‎{title, body, url, tag}‎ מוצפן (‎backend/push.py‎). ‎tag‎ — התראה
 * חדשה מאותו סוג מחליפה את הקודמת במקום להיערם. */
self.addEventListener('push', function (e) {
    let data = {};
    try { data = e.data ? e.data.json() : {}; } catch (err) { data = { body: e.data && e.data.text() }; }
    e.waitUntil(self.registration.showNotification(data.title || 'SmartFin', {
        body: data.body || '',
        tag: data.tag || undefined,
        icon: '/static/icons/icon-192.png',
        badge: '/static/icons/icon-192.png',
        lang: 'he', dir: 'rtl',
        data: { url: data.url || '/' },
    }));
});

/* לחיצה: אם האפליקציה כבר פתוחה — אליה, לעמוד של ההתראה; אחרת חלון חדש.
 * רק כתובות של האתר עצמו. */
self.addEventListener('notificationclick', function (e) {
    e.notification.close();
    let target = '/';
    try {
        const u = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin);
        if (u.origin === self.location.origin) target = u.pathname + u.search;
    } catch (err) { /* ברירת מחדל — הבית */ }
    e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
        for (const c of list) {
            if ('focus' in c) return c.navigate(target).then(function (w) { return (w || c).focus(); });
        }
        return self.clients.openWindow(target);
    }));
});
