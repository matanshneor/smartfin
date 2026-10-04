/* "איך מצרפים בן משפחה" — חלון אחד, בכניסה הראשונה לבית אחרי אשף הפתיחה
 * (מתן, 5.10). השרת מרנדר אותו רק עם ‎?welcome=1‎ ורק כשאין במשפחה אף אחד
 * אחר; כאן הוא נפתח, שולח את ההזמנה, ומוריד את הפרמטר מהכתובת — כדי
 * שרענון לא יפתח אותו שוב. */
(function () {
    const sheet = document.getElementById('welcomeInvite');
    if (!sheet) return;

    if (window.history.replaceState) {
        const url = new URL(window.location.href);
        url.searchParams.delete('welcome');
        window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    }

    const sendBtn = document.getElementById('welcomeSendBtn');
    const close = function () { sheet.hidden = true; };
    document.getElementById('welcomeCloseBtn').addEventListener('click', close);
    sheet.addEventListener('click', function (e) { if (e.target === sheet) close(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });

    sendBtn.addEventListener('click', function () {
        const msg = window.sfInviteMessage(sheet.dataset.code, sheet.dataset.family);
        // בטלפון — חלון השיתוף של המערכת (וואטסאפ ישירות). במחשב, או אם
        // השיתוף נכשל — העתקה, כמו בהגדרות.
        if (navigator.share) {
            navigator.share({ text: msg }).then(close).catch(function (err) {
                if (err && err.name === 'AbortError') return;     // סגרו את חלון השיתוף
                copy(msg);
            });
            return;
        }
        copy(msg);
    });

    function copy(msg) {
        window.copyToClipboard(msg, document.getElementById('welcomeCode')).then(function (copied) {
            if (!copied) return;              // הודעה כבר הוצגה, והקוד מסומן
            sendBtn.textContent = '✓ ההזמנה הועתקה — הדביקו אותה בוואטסאפ';
        });
    }

})();
