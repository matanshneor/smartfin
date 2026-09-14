// רשת ביטחון: אם קישור שחזור סיסמה נחת כאן (fallback ל-SITE_URL),
// מעבירים אותו לעמוד האיפוס עם הטוקן.
if (window.location.hash.includes('type=recovery')) {
    window.location.replace('/reset-password' + window.location.hash);
}


(function () {
    const tabLogin    = document.getElementById('tabLogin');
    const tabSignup   = document.getElementById('tabSignup');
    const loginPanel  = document.getElementById('loginPanel');
    const signupPanel = document.getElementById('signupPanel');

    function showTab(tab) {
        const isSignup = tab === 'signup';
        tabLogin.classList.toggle('active', !isSignup);
        tabSignup.classList.toggle('active', isSignup);
        loginPanel.style.display  = isSignup ? 'none' : 'block';
        signupPanel.style.display = isSignup ? 'block' : 'none';
    }

    tabLogin.addEventListener('click', () => showTab('login'));
    tabSignup.addEventListener('click', () => showTab('signup'));

    // ── שכחתי סיסמה ──
    const forgotPanel = document.getElementById('forgotPanel');
    const forgotError = document.getElementById('forgotError');
    const forgotSuccess = document.getElementById('forgotSuccess');

    document.getElementById('forgotLink').addEventListener('click', function (e) {
        e.preventDefault();
        loginPanel.style.display = 'none';
        forgotPanel.style.display = 'block';
    });

    document.getElementById('backToLoginLink').addEventListener('click', function (e) {
        e.preventDefault();
        forgotPanel.style.display = 'none';
        loginPanel.style.display = 'block';
        forgotError.textContent = '';
        forgotSuccess.textContent = '';
    });

    document.getElementById('forgotBtn').addEventListener('click', function () {
        const email = document.getElementById('forgotEmail').value.trim();
        forgotError.textContent = '';
        forgotSuccess.textContent = '';

        if (!email) {
            forgotError.textContent = 'נא להזין אימייל';
            return;
        }

        const btn = this;
        btn.disabled = true;
        btn.textContent = 'שולח…';

        fetch('/api/auth/forgot', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ email: email }),
        })
        .then(r => r.json())
        .then(function () {
            forgotSuccess.textContent = 'אם האימייל רשום במערכת — קישור איפוס נשלח אליו עכשיו. בדוק גם בספאם.';
            btn.disabled = false;
            btn.textContent = 'שלח קישור איפוס';
        })
        .catch(function () {
            forgotError.textContent = 'שגיאת רשת — נסה שוב';
            btn.disabled = false;
            btn.textContent = 'שלח קישור איפוס';
        });
    });
})();
