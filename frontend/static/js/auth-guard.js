/* סשן שפג: מזוהה פעם אחת, לא בארבעים מקומות.
 *
 * כשה-session נגמר, כל קריאה לשרת חזרה עד היום כדף ההתחברות עם קוד 200,
 * כי fetch עוקב אחרי הפניות בשקט. כל אחת מ-40 הקריאות באפליקציה עשתה
 * r.json() על HTML, נכשלה, ונפלה ל-catch שאומר "שגיאת רשת — נסה שוב".
 * המשתמש היה מנסה שוב ומקבל בדיוק אותו דבר, לנצח, בלי שום רמז שהפתרון
 * הוא להתחבר מחדש. השרת מחזיר עכשיו 401 אמיתי, וכאן מזהים אותו.
 *
 * עוטף את fetch עצמו ולא מוסיף עוזר שצריך לקרוא לו: כך גם קריאה שתיכתב
 * מחר מכוסה בלי לזכור. קובץ נפרד ובלי תלויות, כי הוא נטען גם בעמודים
 * העצמאיים (onboarding) שלא טוענים את core.js.
 */
(function () {
    if (!window.fetch) return;

    const nativeFetch = window.fetch.bind(window);
    let handling = false;

    function isOurs(input) {
        // רק בקשות לשרת שלנו — 401 משירות חיצוני לא אמור לנתק אף אחד
        const url = (typeof input === 'string') ? input : (input && input.url) || '';
        return url.startsWith('/') || url.startsWith(window.location.origin);
    }

    window.fetch = function (input, init) {
        return nativeFetch(input, init).then(function (response) {
            if (response.status === 401 && isOurs(input) && !handling) {
                handling = true;
                if (window.showToast) {
                    window.showToast('ההתחברות הסתיימה — מעבירים אותך להתחברות', 'error');
                }
                // שהות קצרה כדי שההודעה תיקרא; בלעדיה המסך פשוט מתחלף
                setTimeout(function () { window.location.href = '/login'; }, 1400);
            }
            return response;
        });
    };
})();
