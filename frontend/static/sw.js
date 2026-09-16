const CACHE = 'smartfin-v11';

// ה-JS עבר מ-inline בתוך ה-HTML לקבצים נפרדים, ולכן הוא סוף-סוף נהנה
// מה-stale-while-revalidate שכבר היה כאן: עד עכשיו אותן ~1500 שורות ירדו
// מחדש בכל מעבר בין עמודים, כי הן היו חלק מגוף ה-HTML.
const PRECACHE = [
    '/static/css/style.css',
    '/static/js/auth-guard.js',
    '/static/js/core.js',
    '/static/js/transactions.js',
    '/static/js/motion.js',
    '/static/js/pwa.js',
    '/static/js/vendor/chart.umd.min.js',
];

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
        e.respondWith(
            caches.open(CACHE).then(cache =>
                cache.match(e.request).then(cached => {
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

    // עמודים שהתוכן שלהם נגזר מהעוגיות — לעולם לא מהמטמון.
    // השורש מגיש דף נחיתה לאורח, טופס התחברות למכשיר מוכר ודשבורד למי
    // שמחובר; ‎/login נושא את המזהה שנשמר מההתחברות הקודמת. תשובה ישנה
    // כאן משמעותה דף שיווק למשתמש מחובר, או המייל של מישהו אחר בטופס.
    if (url.pathname === '/' || url.pathname === '/login') {
        return;
    }

    // HTML pages: network-first, fall back to cache; אם אין רשת וגם אין
    // מטמון — תשובת "אין חיבור" מסודרת במקום שגיאת דפדפן גולמית.
    e.respondWith(
        fetch(e.request)
            .then(res => {
                if (res.ok) {
                    const clone = res.clone();
                    caches.open(CACHE).then(c => c.put(e.request, clone));
                }
                return res;
            })
            .catch(() =>
                caches.match(e.request).then(cached =>
                    cached || new Response(
                        '<!DOCTYPE html><html lang="he" dir="rtl"><body style="font-family:sans-serif;text-align:center;padding:40px;">אין חיבור לאינטרנט — נסה שוב כשתהיה מחובר</body></html>',
                        { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                    )
                )
            )
    );
});
