// רישום ה-Service Worker והצעת ההתקנה למסך הבית.
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js')
            .catch(function () {});
    });
}

(function () {
    const DISMISS_KEY = 'sf_install_dismissed';
    if (localStorage.getItem(DISMISS_KEY)) return;

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
        localStorage.setItem(DISMISS_KEY, '1');
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
