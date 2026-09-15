// עזרי-ליבה משותפים לכל העמודים: בריחת HTML, טוסט ודיאלוג אישור.
// הועבר מתוך base.html כדי שהדפדפן יוכל לשמור אותו במטמון בין עמודים,
// וכדי לאפשר CSP קפדני שחוסם קוד inline.
// קריאת "אי נתונים" — בלוק <script type="application/json"> שהשרת מרנדר.
// נקרא לפי דרישה ולא פעם אחת מראש, כי כל עמוד מוסיף אי משלו אחרי core.js
// וקריאה מוקדמת לא הייתה רואה אותו.
window.sfData = function (id) {
    const el = document.getElementById(id);
    if (!el) return {};
    try {
        return JSON.parse(el.textContent) || {};
    } catch (e) {
        console.error('sfData: JSON פגום ב-' + id, e);
        return {};
    }
};

// הנתונים הגלובליים מ-base.html זמינים מיד — האי שלהם מופיע לפני הקובץ הזה.
window.SF_PAGE_DATA = window.sfData('sf-page-data');

// בריחת HTML — כל ערך שהמשתמש הזין (שם קטגוריה/פרויקט/אייקון/תיאור)
// חייב לעבור דרך זה לפני הזרקה ל-innerHTML, אחרת שם עם תגית זדונית
// שיצר בן משפחה אחד ירוץ אצל כולם (XSS). זמין גלובלית לכל העמודים.
window.escapeHtml = function (s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};

// ── משוב חושי על עסקה שנכנסה: צליל עדין + נקישה ──
// הצליל מסונתז בזמן אמת (בלי קובץ שמע, בלי בקשת רשת): שני טונים עולים
// קצרים. הרטט מנוסה בשתי דרכים כי אין אחת שעובדת בכל מקום —
// navigator.vibrate באנדרואיד, ומתג switch נסתר שמפעיל את ה-haptic של iOS.
// אין שום דרך לדעת אם המכשיר מושתק, אז לא מנסים: iOS פשוט יבלע את הצליל.
(function () {
    let audioCtx = null;

    function tone(ctx, freq, startAt, dur, peak) {
        const osc  = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, ctx.currentTime + startAt);
        // עטיפת עוצמה רכה — בלי "קליק" בקצוות
        gain.gain.setValueAtTime(0.0001, ctx.currentTime + startAt);
        gain.gain.exponentialRampToValueAtTime(peak, ctx.currentTime + startAt + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + startAt + dur);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + startAt);
        osc.stop(ctx.currentTime + startAt + dur + 0.02);
    }

    window.appFeedback = function () {
        if (localStorage.getItem('sf_feedback_off') === '1') return;

        // צליל
        try {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (Ctx) {
                if (!audioCtx) audioCtx = new Ctx();
                if (audioCtx.state === 'suspended') audioCtx.resume();
                tone(audioCtx, 783.99,  0,    0.16, 0.10);  // סול
                tone(audioCtx, 1174.66, 0.12, 0.30, 0.09);  // רה, אוקטבה מעל
            }
        } catch (err) { /* אין שמע — לא סיבה להיכשל */ }

        // רטט — אנדרואיד בלבד. באייפון אין navigator.vibrate, ושינוי מתג
        // מקוד לא מפעיל את ה-Taptic (נבדק): שם הנקישה מגיעה מהמגע עצמו
        // בכפתור השמירה, שהוא <label> של מתג switch נסתר.
        try {
            if (navigator.vibrate) navigator.vibrate([12, 40, 22]);
        } catch (err) { /* אין רטט — ממשיכים */ }
    };
})();

// ── מערכת משוב גלובלית: toast + דיאלוג אישור ──
(function () {
    const toast = document.getElementById('appToast');
    let toastTimer = null;

    // action = { label, onClick } — כפתור פעולה אופציונלי (למשל "בטל" למחיקה).
    // כשמוצג כפתור, הטוסט נשאר 6 שניות כדי לתת זמן להגיב.
    window.showToast = function (msg, type, action) {
        toast.innerHTML = '';
        const span = document.createElement('span');
        span.className = 'toast-msg';
        span.textContent = msg;
        toast.appendChild(span);
        toast.classList.toggle('error', type === 'error');
        clearTimeout(toastTimer);
        let duration = 2600;
        if (action) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'toast-action';
            btn.textContent = action.label;
            btn.addEventListener('click', function () {
                clearTimeout(toastTimer);
                toast.classList.remove('show');
                action.onClick();
            });
            toast.appendChild(btn);
            duration = 6000;
        }
        toast.classList.add('show');
        toastTimer = setTimeout(function () { toast.classList.remove('show'); }, duration);
    };

    // הודעה שנשמרה לפני רענון דף — מוצגת עכשיו
    const pending = sessionStorage.getItem('sf_toast');
    if (pending) {
        sessionStorage.removeItem('sf_toast');
        setTimeout(function () { window.showToast(pending); }, 350);
    }

    const overlay = document.getElementById('confirmOverlay');
    const titleEl = document.getElementById('confirmTitle');
    const msgEl   = document.getElementById('confirmMessage');
    const yesBtn  = document.getElementById('confirmYes');
    const noBtn   = document.getElementById('confirmNo');
    let resolver  = null;
    let confirmLastFocused = null;

    function closeConfirm(result) {
        overlay.classList.remove('open');
        if (resolver) { resolver(result); resolver = null; }
        if (confirmLastFocused) { confirmLastFocused.focus(); confirmLastFocused = null; }
    }

    window.appConfirm = function (opts) {
        titleEl.textContent  = opts.title || 'לאשר את הפעולה?';
        msgEl.textContent    = opts.message || '';
        yesBtn.textContent   = opts.confirmText || 'מחק';
        noBtn.textContent    = opts.cancelText || 'ביטול';
        // ברירת מחדל: פעולה הרסנית (אדום) — מתאים ל-99% מהשימושים הקיימים
        // (מחיקה). opts.danger === false מציג כפתור ניטרלי לפעולות רגילות.
        yesBtn.classList.toggle('confirm-yes-neutral', opts.danger === false);
        confirmLastFocused = document.activeElement;
        overlay.classList.add('open');
        noBtn.focus(); // ברירת מחדל בטוחה — לא הכפתור ההרסני
        return new Promise(function (resolve) { resolver = resolve; });
    };

    yesBtn.addEventListener('click', function () { closeConfirm(true); });
    noBtn.addEventListener('click', function () { closeConfirm(false); });
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeConfirm(false);
    });

    // Escape סוגר, Tab/Shift+Tab נשארים בתוך הדיאלוג (שני כפתורים בלבד)
    overlay.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { closeConfirm(false); return; }
        if (e.key !== 'Tab') return;
        const focusables = [yesBtn, noBtn];
        const idx = focusables.indexOf(document.activeElement);
        e.preventDefault();
        const next = e.shiftKey
            ? focusables[(idx <= 0 ? focusables.length : idx) - 1]
            : focusables[(idx + 1) % focusables.length];
        next.focus();
    });
})();

