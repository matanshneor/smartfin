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
        // מסך "שכחתי סיסמה" לא נסגר כאן, אז לחיצה על לשונית אחריו הציגה
        // טופס איפוס **מעל** טופס ההרשמה, עם שני פקדי ניווט שחלוקים על
        // היכן המשתמש נמצא — דווקא במסלול שמגיעים אליו כבר מתוסכלים.
        const forgot = document.getElementById('forgotPanel');
        if (forgot) forgot.style.display = 'none';
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
            forgotError.textContent = 'נא להזין מייל';
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
        .then(function (r) {
            return r.json().catch(function () { return {}; })
                .then(function (d) { return { ok: r.ok, data: d || {} }; });
        })
        .then(function (res) {
            btn.disabled = false;
            btn.textContent = 'שליחת קישור איפוס';
            // "נשלח" הופיע גם על 422 (מייל לא תקין), על 429 ועל מגבלת 2 המיילים
            // בשעה של Supabase — והשרת כבר ידע לומר את האמת. מי שהזין מייל
            // שגוי חיכה למייל שלא יגיע. כשהשרת אומר שנכשל, זה מה שמוצג.
            //
            // ההצלחה נשארת עמומה בכוונה ("אם האימייל רשום"), גם כשהוא לא
            // רשום — אחרת הטופס הזה הוא דרך לבדוק אילו מיילים יש במערכת.
            if (!res.ok) {
                forgotError.textContent = res.data.error || 'השליחה נכשלה — נסו שוב בעוד רגע';
                return;
            }
            forgotSuccess.textContent = 'אם המייל רשום במערכת — קישור איפוס נשלח אליו עכשיו. כדאי לבדוק גם בספאם.';
        })
        .catch(function () {
            forgotError.textContent = window.sfNetError();
            btn.disabled = false;
            btn.textContent = 'שליחת קישור איפוס';
        });
    });
})();


/* נעילת שליחה כפולה בטפסי ההתחברות וההרשמה.
 *
 * הטפסים האלה היו הטפסים היחידים באפליקציה בלי נעילה — בכל שאר המקומות
 * הכפתור ננעל (settings.js, onboarding.js, reset-password.js). באפליקציה
 * המותקנת בטלפון אין אפילו ספינר של דפדפן, אז אחרי הקשה המסך פשוט לא
 * מגיב בזמן שהשרת עובד, והמשתמש לוחץ שוב. יומן ההתחברויות מראה שזה קורה
 * בפועל: כמעט כל התחברות רשומה פעמיים בהפרש שנייה. הלחיצה השנייה גם
 * שורפת מהמכסה של 10 לדקה, ומי שחצה אותה נחת על דף שגיאה בלי מוצא.
 */
(function () {
    function guardSubmit(form, busyText) {
        if (!form) return;
        const btn = form.querySelector('button[type="submit"]');
        if (!btn) return;
        const idleText = btn.textContent;

        function release() {
            btn.disabled = false;
            btn.textContent = idleText;
        }

        form.addEventListener('submit', function () {
            if (btn.disabled) return;
            btn.disabled = true;
            btn.textContent = busyText;
            // שסתום ביטחון: אם השליחה לא הובילה לניווט (נפילת רשת), הכפתור
            // חוזר לפעולה. עדיף ניסיון חוזר מטופס מת שאי אפשר לצאת ממנו.
            setTimeout(release, 12000);
        });

        // חזרה לעמוד עם "אחורה" מגישה אותו מזיכרון הדפדפן, והכפתור
        // היה חוזר נעול מהפעם הקודמת
        window.addEventListener('pageshow', function (e) { if (e.persisted) release(); });
    }

    guardSubmit(document.getElementById('loginPanel'),  'מתחברים…');
    guardSubmit(document.getElementById('signupPanel'), 'נרשמים…');
})();
