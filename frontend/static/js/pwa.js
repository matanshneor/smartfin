// רישום ה-Service Worker והצעת ההתקנה למסך הבית.
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js')
            .catch(function () {});
    });
}

(function () {
    const DISMISS_KEY = 'sf_install_dismissed';
    // ‎try/catch‎: זו הגישה האחרונה בריפו ל-‎localStorage‎ שלא הייתה
    // מוגנת. ב-Safari עם עוגיות חסומות, בגלישה פרטית או ב-Lockdown
    // Mode הקריאה **זורקת** — וכאן, בשורה הראשונה של ה-IIFE, היא
    // הורגת את כל הקובץ. אותה נפילה בדיוק שקרתה ל-core.js.
    try {
        if (localStorage.getItem(DISMISS_KEY)) return;
    } catch (e) { /* אין אחסון — מציגים את ההצעה, במקום לא כלום */ }

    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
    if (isStandalone) return;

    const banner  = document.getElementById('installBanner');
    const text    = document.getElementById('installBannerText');
    const actionBtn = document.getElementById('installBannerAction');
    const closeBtn  = document.getElementById('installBannerClose');
    let deferredPrompt = null;

    function dismiss() {
        banner.style.display = 'none';
        try {
            localStorage.setItem(DISMISS_KEY, '1');
        } catch (e) { /* לא נזכר — הבאנר יחזור, וזה עדיף על קריסה */ }
    }
    closeBtn.addEventListener('click', dismiss);

    const isIOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;
        text.textContent = 'התקינו את SmartFin למסך הבית לגישה מהירה יותר';
        actionBtn.style.display = '';
        banner.style.display = '';
    });

    actionBtn.addEventListener('click', function () {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.finally(dismiss);
    });

    window.addEventListener('appinstalled', dismiss);

    // ל-iOS אין beforeinstallprompt בכלל — מציגים הנחיה סטטית בלבד
    if (isIOS) {
        text.textContent = 'להתקנת SmartFin: הקש על שיתוף ← הוסף למסך הבית';
        banner.style.display = '';
    }
})();
