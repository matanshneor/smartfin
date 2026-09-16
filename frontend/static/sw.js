const CACHE = 'smartfin-v20';

// אין טעינה-מראש.
//
// הכתובות של הנכסים נושאות עכשיו חתימת תוכן (‎?v=…‎) שנקבעת בשרת, ורשימה
// קבועה כאן לא יכולה לדעת אותה — היא הייתה מורידה כתובות בלי חתימה שאף
// עמוד לא מבקש, כלומר הורדה כפולה של כל קובץ ומטמון שלא נוגעים בו לעולם.
//
// וזה ממילא לא נחוץ יותר: כתובת חתומה מוגשת עם תוקף של שנה, אז הדפדפן
// שומר אותה בעצמו כבר מהביקור הראשון. מה שמגיע לכאן נשמר בזמן אמת למטה.
const PRECACHE = [];

self.addEventListener('install', function (e) {
    e.waitUntil(
        caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
    );
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
        '<link rel="stylesheet" href="/static/css/style.css"></head>' +
        '<body class="auth-body"><div class="auth-container">' +
        '<div class="empty-state">' +
        '<p class="empty-icon">📡</p>' +
        '<p class="empty-text">אין חיבור לאינטרנט</p>' +
        '<p class="empty-sub">המספרים שלכם מחכים ברגע שהחיבור יחזור. ' +
        'לא מוצגים כאן נתונים ישנים, כדי שלא תסתמכו על מספר שכבר לא נכון.</p>' +
        '<button class="submit-btn" onclick="location.reload()">נסו שוב</button>' +
        '</div></div></body></html>',
        { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
}

self.addEventListener('fetch', function (e) {
    // Only intercept same-origin GET requests
    if (e.request.method !== 'GET') return;
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
                    }).catch(() => cached);
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
        e.respondWith(fetch(e.request).catch(() => offlinePage()));
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
