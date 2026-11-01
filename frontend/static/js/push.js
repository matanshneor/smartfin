/* התראות לטלפון — מופעלות כברירת מחדל (מתן, 1.11).
 *
 * "שההתראות יהיו מופעלות לכולם ויהיה אפשר לבטל". הדפדפן לא מאפשר להירשם
 * להתראות בלי לחיצה של המשתמש על "אפשר" בחלון שלו — זו לא החלטה שלנו. אז
 * הכי קרוב שאפשר:
 *   · מי שכבר אישר בעבר — נרשם אוטומטית, בשקט, בכל מכשיר שנכנס ממנו.
 *   · מי שעוד לא נשאל — פס קטן מעל התפריט התחתון, פעם אחת: "הפעלה". לחיצה
 *     אחת, והחלון של הטלפון. ✕ — לא נשאלים שוב במכשיר הזה ("שלא יציק
 *     להם כל שבוע", מתן 1.11). אפשר תמיד להפעיל בהגדרות ← התראות.
 *   · מי שכיבה בהגדרות — לא נשאל ולא נרשם שוב במכשיר הזה.
 * באייפון זה עובד רק מהאפליקציה המותקנת — מחוץ לה אין שם התראות בכלל.
 *
 * ‎window.sfPush‎ — גם המתג בהגדרות עובד דרך כאן. */
(function () {
    'use strict';
    const key = (window.SF_PAGE_DATA || {}).pushKey;
    const OFF = 'sf_push_off';
    const ASKED = 'sf_push_asked';

    const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    const iOS = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
                (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
    const supported = !!key && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

    function store(name, value) {
        try { if (value === null) localStorage.removeItem(name); else localStorage.setItem(name, value); }
        catch (e) { /* בלי זיכרון — לכל היותר נשאל שוב */ }
    }
    function read(name) {
        try { return localStorage.getItem(name); } catch (e) { return null; }
    }
    function keyBytes(b64) {
        const s = (b64 + '='.repeat((4 - b64.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/');
        return Uint8Array.from(atob(s), function (c) { return c.charCodeAt(0); });
    }
    function post(url, body) {
        return fetch(url, { method: 'POST', credentials: 'same-origin',
                            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
            .then(function (r) {
                return r.json().catch(function () { return {}; }).then(function (d) {
                    if (!r.ok) throw new Error(d.error || '');
                    return d;
                });
            });
    }
    function registration() { return navigator.serviceWorker.ready; }

    /* ‎'on'‎ — רשום; ‎'off'‎ — לא; ‎'blocked'‎ — חסום בהגדרות הטלפון;
     * ‎'unsupported'‎ — אין כאן התראות (באייפון: לא מהאפליקציה המותקנת). */
    function state() {
        if (!supported) return Promise.resolve('unsupported');
        if (Notification.permission === 'denied') return Promise.resolve('blocked');
        return registration().then(function (reg) { return reg.pushManager.getSubscription(); })
            .then(function (sub) { return sub && read(OFF) !== '1' ? 'on' : 'off'; });
    }

    function subscribe(reg) {
        return reg.pushManager.getSubscription().then(function (sub) {
            return sub || reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
        }).then(function (sub) { return post('/api/push/subscribe', sub.toJSON()); });
    }

    /* חייב לרוץ מתוך לחיצה — אחרת ספארי לא מציג את חלון האישור */
    function enable() {
        store(OFF, null);
        return Notification.requestPermission().then(function (perm) {
            if (perm !== 'granted') throw new Error('כדי לקבל התראות צריך לאשר אותן בחלון של הטלפון');
            return registration().then(subscribe);
        });
    }

    function disable() {
        store(OFF, '1');
        return registration().then(function (reg) { return reg.pushManager.getSubscription(); })
            .then(function (sub) {
                if (!sub) return post('/api/push/unsubscribe', {});
                const endpoint = sub.endpoint;
                return sub.unsubscribe().then(function () { return post('/api/push/unsubscribe', { endpoint: endpoint }); });
            });
    }

    window.sfPush = { supported: supported, iOS: iOS, standalone: standalone,
                      state: state, enable: enable, disable: disable };

    if (!supported || read(OFF) === '1') return;

    // כבר אישרו בעבר: נרשמים בשקט (ומוודאים שהשרת יודע — פעם בכניסה)
    if (Notification.permission === 'granted') {
        let told = false;
        try { told = sessionStorage.getItem('sf_push_told') === '1'; } catch (e) { /* */ }
        if (!told) {
            registration().then(subscribe).then(function () {
                try { sessionStorage.setItem('sf_push_told', '1'); } catch (e) { /* */ }
            }).catch(function () { /* בכניסה הבאה */ });
        }
        return;
    }
    if (Notification.permission !== 'default') return;

    // עוד לא נשאלו: הפס, אם אין כרגע את הפס של "הוסיפו למסך הבית"
    const bar = document.getElementById('pushBar');
    if (!bar || document.body.classList.contains('has-install-bar')) return;
    if (read(ASKED) === '1') return;
    function hide() { bar.hidden = true; document.body.classList.remove('has-install-bar'); }
    bar.hidden = false;
    document.body.classList.add('has-install-bar');
    document.getElementById('pushBarClose').addEventListener('click', function () {
        store(ASKED, '1');
        hide();
    });
    document.getElementById('pushBarGo').addEventListener('click', function () {
        enable().then(function () {
            hide();
            if (window.showToast) window.showToast('ההתראות הופעלו');
        }).catch(function (err) {
            store(ASKED, '1');
            hide();
            if (window.showToast && err && err.message) window.showToast(err.message, 'error');
        });
    });
})();
