/* נעילה ב-Face ID — צד הדפדפן (מתן, 13.10). רק בטלפון שהגדיר (‎data-face-lock‎).
 *
 * השרת נועל אחרי 5 דקות בלי בקשה. שני דברים כאן מתאימים את זה ל"5 דקות ברקע":
 *   • דופק כל דקה כשהאפליקציה על המסך — קריאה בלי לגעת במסך לא נועלת.
 *   • חזרה מהרקע אחרי יותר מ-5 דקות: האייפון מחזיר את העמוד מהזיכרון, בלי
 *     בקשה לשרת — אז כאן עוברים למסך הנעילה לפני שמשהו מוצג. */
(function () {
    'use strict';
    if (!document.body || !document.body.hasAttribute('data-face-lock')) return;
    const LOCK_AFTER = 5 * 60 * 1000;
    let hiddenAt = null;

    function lockNow() {
        window.location.replace('/unlock?next=' + encodeURIComponent(location.pathname + location.search));
    }
    function beat() {
        if (document.hidden) return;
        fetch('/api/alive', { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .catch(function () { /* בלי רשת — השרת יחליט בבקשה הבאה */ });
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) { hiddenAt = Date.now(); return; }
        if (hiddenAt && Date.now() - hiddenAt > LOCK_AFTER) { lockNow(); return; }
        hiddenAt = null;
        beat();
    });
    // ‎pageshow‎ מהמטמון של הדפדפן (חזרה אחורה / פתיחה מחדש) — אותה בדיקה
    window.addEventListener('pageshow', function (e) {
        if (e.persisted && hiddenAt && Date.now() - hiddenAt > LOCK_AFTER) lockNow();
    });
    setInterval(beat, 60 * 1000);
})();
