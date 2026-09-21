/* ההודעה שמועתקת בשיתוף קוד הזמנה.
 *
 * עד היום הועתקו שישה תווים ותו לא. מי שקיבל "K4F2QX" בוואטסאפ קיבל
 * שישה תווים בלי שם, בלי קישור ובלי רמז מה לעשות איתם — בזמן שדף
 * הנחיתה מוכר את זה כ"מזמינים את בני הבית עם קוד בן שישה תווים".
 *
 * הקוד נשאר בשורה נפרדת ובלי סימני פיסוק צמודים, כדי שאפשר יהיה
 * לסמן אותו בלחיצה ארוכה בלי לגרור אליו נקודה. */
window.sfInviteMessage = function (code, familyName) {
    const who = familyName ? ('\u200f"' + familyName + '"') : '\u200fהמשפחה שלנו';
    return 'הצטרפו אליי ל-SmartFin — התקציב המשותף של ' + who + '.\n\n'
         + 'קוד ההזמנה:\n' + code + '\n\n'
         + window.location.origin + '/signup';
};

/* העתקה ללוח, עם נפילה חזרה.
 *
 * ‎navigator.clipboard‎ נכשל יותר ממה שנדמה: הרשאה שנדחתה, הקשר לא-מאובטח,
 * דפדפן-בתוך-אפליקציה (הקישור נפתח מוואטסאפ), או שהאובייקט פשוט לא קיים.
 * הקוד הקודם קרא ל-‎.then()‎ בלי ‎.catch‎, אז כישלון היה דחייה לא-מטופלת:
 * הכפתור לא השתנה, לא הופיעה הודעה, לא קרה כלום.
 *
 * וזו הפעולה שהופכת משפחה למשפחה — בלי להעביר את הקוד, אף אחד לא מצטרף.
 *
 * הנפילה חזרה בוחרת את הטקסט על המסך, כך שלמשתמש נשארת פעולה אחת
 * (העתק) במקום לתהות למה כלום לא קורה. */
window.copyToClipboard = function (text, el) {
    function selectInstead() {
        try {
            const range = document.createRange();
            range.selectNodeContents(el);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            if (window.showToast) window.showToast('הקוד מסומן — העתיקו אותו ידנית');
        } catch (e) {
            if (window.showToast) window.showToast('לא הצלחנו להעתיק. הקוד: ' + text, 'error');
        }
        return false;
    }

    if (!navigator.clipboard || !navigator.clipboard.writeText) {
        return Promise.resolve(selectInstead());
    }
    return navigator.clipboard.writeText(text)
        .then(function () { return true; })
        .catch(function () { return selectInstead(); });
};
