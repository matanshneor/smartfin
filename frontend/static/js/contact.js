/* כתובת הקשר, מורכבת בדפדפן.
 *
 * העמודים המשפטיים פתוחים לכל האינטרנט ומסומנים לאינדוקס, וזה בדיוק
 * מה שבוטים סורקים: הם מחפשים ‎mailto:‎ ומחרוזות עם ‎@‎. כתובת שיושבת
 * שם כטקסט גלוי נקצרת תוך ימים.
 *
 * ההרכבה כאן שומרת על מה שחשוב: הכתובת היא טקסט אמיתי ב-DOM, אז
 * קורא מסך מקריא אותה, אפשר לסמן ולהעתיק, והקישור עובד. סורק שלא
 * מריץ JavaScript — והרוב לא — לא רואה כלום.
 *
 * ל-‎<noscript>‎ יש ניסוח קריא לבני אדם, כדי שגם בלי JavaScript אפשר
 * יהיה ליצור קשר. זו לא הגנה מושלמת, והיא לא אמורה להיות: המטרה היא
 * לחסום קציר אוטומטי, לא אדם שמחפש.
 */
(function () {
    document.querySelectorAll('[data-contact]').forEach(function (el) {
        const user   = el.dataset.user;
        const domain = el.dataset.domain;
        if (!user || !domain) return;

        const address = user + '@' + domain;
        const link = document.createElement('a');
        link.href = 'mailto:' + address;
        link.textContent = address;
        el.textContent = '';
        el.appendChild(link);
    });
})();
