/* מצב כהה — ידני בלבד (מתן, 30.9 — סבב 6, פריט 4).
 *
 * נטען ב-<head> לפני שהעמוד מצויר, כדי שלא יהבהב לבן לרגע. קובץ ולא
 * שורה בתוך התבנית: ה-CSP חוסם סקריפטים בתוך העמוד. הבחירה נשמרת בטלפון
 * (לא לכל המשפחה) — מי שאוהב כהה לא כופה אותו על בן הזוג. */
(function () {
    try {
        if (localStorage.getItem('sf_theme') === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
        // גודל טקסט (סבב 6, פריט 9) — אותו רגע ואותה סיבה: בלי קפיצה בטעינה
        const size = localStorage.getItem('sf_text_size');
        if (size === 'large' || size === 'xlarge') {
            document.documentElement.setAttribute('data-text-size', size);
        }
    } catch (e) { /* אין אחסון — נשארים בבהיר ובגודל הרגיל */ }
})();
