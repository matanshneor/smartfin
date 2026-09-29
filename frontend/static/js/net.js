/* מצב אופליין: להגיד לפני, לא אחרי.
 *
 * עד היום לא היה באפליקציה שום מושג שאין רשת. מישהו בחניון תת-קרקעי
 * הקליד עסקה, לחץ שמור, וקיבל "שגיאת רשת — נסה שוב" — אותה הודעה
 * שמוצגת גם כשהשרת נפל וגם כשיש באג. הוא ניסה שוב, קיבל את אותו דבר,
 * ולא היה שום רמז שהבעיה היא בו ולא בנו, ושהפתרון הוא לצאת מהחניון.
 *
 * שתי שכבות, שתיהן קטנות:
 *   · פס עליון שמופיע כשאין חיבור — כדי שההפתעה תגיע לפני ההקלדה.
 *   · הודעת שגיאה שיודעת להבדיל בין "אין רשת" ל"משהו השתבש".
 *
 * מה שאין כאן במכוון: תור שמסנכרן עסקאות כשהרשת חוזרת. זו מערכת
 * סנכרון שלמה — כפילויות, קונפליקטים, ועסקאות שנרשמות שעות אחרי
 * שהמשתמש שכח מהן. באפליקציה כספית זה גרוע מהבעיה שהוא פותר.
 *
 * בלי תלויות, כי הוא נטען גם בעמודים העצמאיים (התחברות, איפוס סיסמה,
 * onboarding) שלא טוענים את core.js.
 */
(function () {
    var GENERIC = 'שגיאת רשת — נסה שוב';
    var OFFLINE = 'אין חיבור לאינטרנט — נסו שוב כשהחיבור יחזור';

    /* מסתמכים רק על הכיוון האמין.
     *
     * ‎navigator.onLine === true‎ אומר רק שיש ממשק רשת פעיל — הוא מחזיר
     * true גם כשמחוברים לראוטר בלי אינטרנט, אז אי אפשר להסיק ממנו
     * שהכול בסדר. ‎false‎, לעומת זאת, אמין: הדפדפן יודע בוודאות שאין
     * חיבור. לכן הוא מוסיף מידע כשהוא שלילי, ולא גורע כשהוא חיובי. */
    function definitelyOffline() {
        return navigator.onLine === false;
    }

    /* ההודעה שכל מקומות הכישלון ברשת מציגים. פונקציה ולא מחרוזת כי
     * התשובה תלויה במצב ברגע הכישלון, לא ברגע טעינת הקובץ. */
    window.sfNetError = function () {
        return definitelyOffline() ? OFFLINE : GENERIC;
    };

    /* רשימה מהשרת (קטגוריות, בני משפחה, פרויקטים) — או שגיאה. אף פעם לא
     * משהו באמצע.
     *
     * ‎fetch().then(r => r.json())‎ לא בודק את הסטטוס: תשובת 500 או 429
     * היא ‎{error: …}‎ — והיא נשמרה במטמון כאילו היא הרשימה. מאותו רגע כל
     * לחיצה על + נפלה על ‎.filter‎ של אובייקט והציגה "שגיאת רשת", גם אחרי
     * שהשרת התאושש, כי המטמון כבר "מלא". דחייה כאן לא נשמרת בשום מטמון,
     * אז הלחיצה הבאה מנסה שוב. */
    window.sfFetchList = function (url) {
        return fetch(url).then(function (r) {
            return r.json().catch(function () { return null; }).then(function (data) {
                if (!r.ok || !Array.isArray(data)) {
                    throw new Error((data && data.error) || ('HTTP ' + r.status));
                }
                return data;
            });
        });
    };

    var banner = null;

    function showBanner() {
        if (!banner) {
            banner = document.createElement('div');
            banner.className = 'net-banner';
            // status ולא alert: זו הודעת מצב, לא משהו שצריך לקטוע בשבילו
            // את מה שקורא המסך מקריא כרגע
            banner.setAttribute('role', 'status');
            banner.textContent =
                'אין חיבור לאינטרנט. מה שהקלדתם נשאר על המסך — נסו שוב כשהחיבור יחזור.';
            document.body.appendChild(banner);
        }
        banner.hidden = false;
    }

    function hideBanner() {
        if (!banner || banner.hidden) return;
        banner.hidden = true;
        if (window.showToast) window.showToast('החיבור חזר');
    }

    window.addEventListener('offline', showBanner);
    window.addEventListener('online', hideBanner);

    // מי שפתח את האפליקציה כשכבר אין חיבור לא מקבל אירוע — רק מצב
    if (definitelyOffline()) showBanner();
})();
