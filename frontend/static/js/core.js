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

/* סכום כסף לתצוגה — אותו כלל כמו ‎format_money‎ בשרת (backend/money.py):
 * אגורות רק כשיש. ‎12.5 → "12.50"‎, ‎180 → "180"‎. בלי ₪ ובלי סימן.
 * ‎withCents‎ כופה שתי ספרות — לאנימציה שמסתיימת בסכום עם אגורות, כדי
 * שהספרות לא יקפצו מ-"12" ל-"12.50" בפריים האחרון. */
window.sfMoney = function (value, withCents) {
    const amount = Math.round((Number(value) || 0) * 100) / 100;
    const cents = withCents || amount !== Math.round(amount);
    return amount.toLocaleString('en-US', {
        minimumFractionDigits: cents ? 2 : 0,
        maximumFractionDigits: cents ? 2 : 0,
    });
};

/* הודעה להצגה אחרי טעינה מלאה של הדף ("העסקה נוספה").
 *
 * ‎sessionStorage‎ זורק בדפדפן שחוסם אחסון (מצב פרטי מחמיר, Lockdown).
 * הקריאה הזאת ישבה בלי הגנה בתוך ‎.then‎ של שמירה שכבר הצליחה — והחריגה
 * נפלה ל-‎.catch‎ של הרשת: המשתמש ראה "שגיאת רשת", הכפתור השתחרר, והוא
 * לחץ שוב ויצר עותק. בלי אחסון מוותרים על ההודעה, לא על הטעינה. */
/* "מספר + שם עצם" — אותו כלל כמו ‎count_of‎ ב-backend/wording.py:
 * ‎sfCount(1, 'עסקה אחת', 'עסקאות')‎ → "עסקה אחת", ‎sfCount(3, …)‎ → "3 עסקאות". */
window.sfCount = function (n, one, many) {
    n = parseInt(n, 10) || 0;
    return n === 1 ? one : n + ' ' + many;
};

window.sfToastAfterReload = function (message) {
    try { sessionStorage.setItem('sf_toast', message); } catch (e) { /* בלי הודעה, לא בלי טעינה */ }
};

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
/* ── תנועה פיזיקלית, משותפת לחלון, לשורות ולכרטיס "השבוע" (מתן, 7.10 — בנוסח אפל) ── */

// קפיץ במונחים של אפל: ‎response‎ — כמה מהר מגיעים (שניות), ‎damping‎ — 1
// בלי קפיצה, פחות מ-1 קופץ קצת מעבר. מתחיל מהמקום ומהמהירות הנוכחיים,
// אז אין תפר בין האצבע לתנועה. מחזיר פונקציה שעוצרת אותו באמצע.
window.sfSpring = function (from, to, v0, response, damping, paint, done, until) {
    const k = Math.pow(2 * Math.PI / response, 2), c = 4 * Math.PI * damping / response;
    let x = from, v = v0, last = performance.now(), raf;
    raf = requestAnimationFrame(function frame(now) {
        const dt = Math.min((now - last) / 1000, 0.064);
        last = now;
        const n = Math.max(1, Math.ceil(dt / 0.004));
        for (let i = 0; i < n; i++) { v += (-k * (x - to) - c * v) * dt / n; x += v * dt / n; }
        if ((until && until(x)) || (Math.abs(x - to) < 0.5 && Math.abs(v) < 8)) {
            paint(until ? x : to); done(); return;
        }
        paint(x);
        raf = requestAnimationFrame(frame);
    });
    return function () { cancelAnimationFrame(raf); };
};

// לאן הייתה מגיעה תנועה במהירות הזו אילו המשיכה לדעוך. ‎0.998‎ — כמו
// גלילה; ‎0.99‎ — קצר יותר, למרחקים קטנים כמו שורה.
window.sfProject = function (v, rate) {
    rate = rate || 0.998;
    return (v / 1000) * rate / (1 - rate);
};

// מעבר לגבול — כל פיקסל נוסף זז פחות (כמו בקצה של רשימה באייפון)
window.sfRubber = function (over, dim) { return (over * dim * 0.55) / (dim + 0.55 * Math.abs(over)); };

// מהירות (px/s) מ-‎100ms‎ האחרונות של הגרירה, לא מכולה. לפחות פריים
// אחד: הדפדפן מאחד תנועות מהירות, ושתי דגימות באותה אלפית שנייה נתנו
// מהירות אפס — והנפה חזקה לא עשתה כלום.
window.sfVelocity = function (samples, now) {
    const end = samples[samples.length - 1];
    let first = end;
    for (let i = samples.length - 1; i >= 0 && now - samples[i].t <= 100; i--) first = samples[i];
    return (end.p - first.p) / Math.max(end.t - first.t, 16) * 1000;
};

/* אזור שנפתח ונסגר בהחלקה של הגובה ולא בקפיצה (מתן, 7.10 — סבב תנועה, סעיף 5).
 * ‎apply(open)‎ עושה את ההחלפה עצמה (מחלקה) — בפתיחה מיד ואז מגדלים מ-0, בסגירה
 * מכווצים ורק בסוף מחליפים. לחיצה באמצע — ממשיכים מהגובה שעל המסך עכשיו.
 * ‎animate‎ ולא CSS, ולכן תנועה מופחתת נבדקת כאן: הכלל הכללי לא חל עליו. */
window.sfReveal = function (body, open, apply) {
    const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (calm || !body || !body.animate) { apply(open); return; }
    const from = body.sfAnim ? body.offsetHeight : null;     // באמצע תנועה קודמת
    if (body.sfAnim) { body.sfAnim.cancel(); body.sfAnim = null; }
    if (open) apply(true);
    const cs = getComputedStyle(body);
    const full = { height: body.offsetHeight + 'px', opacity: 1,
                   paddingTop: cs.paddingTop, paddingBottom: cs.paddingBottom,
                   marginTop: cs.marginTop, marginBottom: cs.marginBottom,
                   borderTopWidth: cs.borderTopWidth, borderBottomWidth: cs.borderBottomWidth };
    const none = { height: '0px', opacity: 0, paddingTop: '0px', paddingBottom: '0px',
                   marginTop: '0px', marginBottom: '0px', borderTopWidth: '0px', borderBottomWidth: '0px' };
    const start = Object.assign({}, open ? none : full);
    if (from !== null) { start.height = from + 'px'; start.opacity = open ? 0.5 : 1; }
    body.style.overflow = 'hidden';
    const anim = body.animate([start, open ? full : none],
        { duration: open ? 220 : 180, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' });
    body.sfAnim = anim;
    anim.onfinish = function () {
        body.sfAnim = null;
        body.style.overflow = '';
        if (!open) apply(false);
    };
};

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
        try {
            if (localStorage.getItem('sf_feedback_off') === '1') return;
        } catch (e) { /* אין אחסון — ברירת המחדל היא שהמשוב פעיל */ }

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
    let toastHide = null;

    // האם הפעולה האחרונה הייתה במקלדת — כדי להעביר את המיקוד ל"בטל" רק
    // למי שמנווט במקלדת, ולא לקפוץ למי שנגע במסך
    let lastInputWasKeyboard = false;
    document.addEventListener('keydown', function () { lastInputWasKeyboard = true; }, true);
    document.addEventListener('pointerdown', function () { lastInputWasKeyboard = false; }, true);

    // "בטל" לא נעלם מתחת לאצבע או למיקוד: 6 שניות לא מספיקות למי שהגיע
    // אליו במקלדת או מתלבט עם העכבר מעליו
    function holdToast() { clearTimeout(toastTimer); }
    function releaseToast() {
        clearTimeout(toastTimer);
        if (toastHide) toastTimer = setTimeout(toastHide, 2500);
    }
    toast.addEventListener('mouseenter', holdToast);
    toast.addEventListener('mouseleave', releaseToast);
    toast.addEventListener('focusin', holdToast);
    toast.addEventListener('focusout', releaseToast);

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
        // הודעה ארוכה ("העסקה נוספה. עברתם את התקציב של…") צריכה זמן לקריאה
        let duration = msg.length > 40 ? 4500 : 2600;
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
        toastHide = function () { toast.classList.remove('show'); toastHide = null; };
        toastTimer = setTimeout(toastHide, duration);
        // מי שמחק במקלדת איבד את המיקוד יחד עם השורה; "בטל" הוא המקום
        // הטבעי שלו עכשיו — אחרת הוא צריך לעבור את כל העמוד ב-Tab ב-6 שניות
        const actionBtn = toast.querySelector('.toast-action');
        if (actionBtn && lastInputWasKeyboard) actionBtn.focus({ preventScroll: true });
    };

    // הודעה שנשמרה לפני רענון דף — מוצגת עכשיו
    // גישה לאחסון יכולה לזרוק — גלישה פרטית, אחסון חסום, או סביבה
    // שאין בה אותו בכלל. השורה הזאת רצה בטעינת הקובץ, אז חריגה כאן
    // הפילה את **כל** core.js: אין toast, אין דיאלוג אישור, אין רענון
    // רך. תופעת לוואי מועילה: ככה זה התגלה, כשהבדיקות רצו ב-node 22.
    let pending = null;
    try {
        pending = sessionStorage.getItem('sf_toast');
    } catch (e) { /* אין אחסון — ההודעה הדחויה פשוט לא תוצג */ }
    // הודעה מהשרת (‎_notice.html‎) — למשל "המשפחה שלך השתנתה"
    const noticeEl = document.getElementById('sfNotice');
    if (!pending && noticeEl) {
        try { pending = JSON.parse(noticeEl.textContent); } catch (e) {}
    }
    if (pending) {
        try { sessionStorage.removeItem('sf_toast'); } catch (e) {}
        setTimeout(function () { window.showToast(pending); }, 350);
    }

    const overlay = document.getElementById('confirmOverlay');
    const titleEl = document.getElementById('confirmTitle');
    const msgEl   = document.getElementById('confirmMessage');
    const yesBtn  = document.getElementById('confirmYes');
    const noBtn   = document.getElementById('confirmNo');
    const choiceEl = document.getElementById('confirmChoice');
    let resolver  = null;
    let withChoice = false;
    let confirmLastFocused = null;

    function closeConfirm(result) {
        // עם ‎choices‎ האישור מחזיר את מה שנבחר ולא ‎true‎
        if (result === true && withChoice) result = choiceEl.value;
        overlay.classList.remove('open');
        if (resolver) { resolver(result); resolver = null; }
        if (confirmLastFocused) { confirmLastFocused.focus(); confirmLastFocused = null; }
    }

    /* שלוש תוצאות ולא שתיים:
     *   true  — נבחר כפתור האישור
     *   false — נבחר כפתור הביטול
     *   null  — נסיגה: Escape, ✕, או לחיצה מחוץ לדיאלוג
     *
     * ההבחנה נחוצה כשיש שתי שאלות ברצף. במחיקת פרויקט, השאלה השנייה היא
     * "מה לעשות עם העסקאות" — ובריחה ממנה פורשה כ"השאר אותן", כך שהפרויקט
     * נמחק בכל זאת. מי שנבהל ולחץ מחוץ לדיאלוג התכוון לסגת, ולפרויקט אין
     * ביטול-מחיקה.
     *
     * ‎null‎ נבחר במכוון כי הוא falsy: כל הקוראים הקיימים בודקים ‎if (!ok)‎
     * וממשיכים לעבוד בלי שינוי. מי שצריך את ההבחנה בודק ‎=== null‎.
     *
     * ‎opts.choices‎ (‏[{value, label}]) מוסיף רשימה לבחירה מתחת להודעה, ואז
     * האישור מחזיר את ה-‎value‎ שנבחר במקום ‎true‎. */
    window.appConfirm = function (opts) {
        withChoice = !!(opts.choices && opts.choices.length);
        choiceEl.hidden = !withChoice;
        choiceEl.innerHTML = '';
        (opts.choices || []).forEach(function (c) {
            const o = document.createElement('option');
            o.value = c.value;
            o.textContent = c.label;
            choiceEl.appendChild(o);
        });
        titleEl.textContent  = opts.title || 'לאשר את הפעולה?';
        msgEl.textContent    = opts.message || '';
        yesBtn.textContent   = opts.confirmText || 'מחיקה';
        noBtn.textContent    = opts.cancelText || 'ביטול';
        // ברירת מחדל: פעולה הרסנית (אדום) — מתאים ל-99% מהשימושים הקיימים
        // (מחיקה). opts.danger === false מציג כפתור ניטרלי לפעולות רגילות.
        yesBtn.classList.toggle('confirm-yes-neutral', opts.danger === false);
        confirmLastFocused = document.activeElement;
        overlay.classList.add('open');
        // בפריים הבא: הדיאלוג מוסתר ב-visibility כשהוא סגור, ואי אפשר
        // למקד אלמנט בתוך אב מוסתר
        requestAnimationFrame(function () {
            noBtn.focus(); // ברירת מחדל בטוחה — לא הכפתור ההרסני
        });
        return new Promise(function (resolve) { resolver = resolve; });
    };

    /* מחיקת קטגוריה — משותף להגדרות ולעמוד הפרויקט.
     *
     * אין עסקה בלי קטגוריה: קודם שואלים את השרת כמה עסקאות יש בה ולאן
     * אפשר להעביר אותן, ואז שואלים את המשתמש באותו דיאלוג. השרת אוכף את
     * אותו כלל בעצמו (409 בלי יעד), כך שהשאלה כאן היא נוחות ולא ההגנה.
     * מחזיר ‎Promise‎ של ‎true‎ כשהקטגוריה נמחקה. */
    let deletingCategory = false;
    window.sfDeleteCategory = function (baseUrl, name) {
        // נגיעה כפולה ב-✕ פתחה שתי שאלות ברצף, והתשובה לראשונה נבלעה בשנייה
        if (deletingCategory) return Promise.resolve(false);
        deletingCategory = true;
        function json(r) {
            return r.json().catch(function () { return {}; })
                .then(function (d) { return { ok: r.ok, d: d }; });
        }
        let usage = null;
        return fetch(baseUrl + '/usage').then(json).then(function (res) {
            if (!res.ok || res.d.blocked) {
                window.showToast(res.d.blocked || res.d.error || 'המחיקה נכשלה', 'error');
                return false;
            }
            usage = res.d;
            const count = usage.count || 0;
            const opts = { title: 'למחוק את "' + name + '"?', confirmText: 'מחיקת הקטגוריה' };
            if (count) {
                opts.message = (count === 1 ? 'יש בקטגוריה הזו עסקה אחת' : 'יש בקטגוריה הזו ' + count + ' עסקאות')
                    + '. לאיזו קטגוריה להעביר ' + (count === 1 ? 'אותה' : 'אותן') + '?';
                opts.choices = usage.alternatives.map(function (c) {
                    return { value: c.id, label: c.icon + ' ' + c.name };
                });
                opts.confirmText = 'העברה ומחיקה';
            } else {
                opts.message = 'אין בה עסקאות.';
            }
            return window.appConfirm(opts);
        }).then(function (answer) {
            if (!answer) return false;
            const target = usage.count ? answer : null;
            const url = baseUrl + (target ? '?move_to=' + encodeURIComponent(target) : '');
            return fetch(url, { method: 'DELETE' }).then(json).then(function (res) {
                if (!res.ok) {
                    window.showToast(res.d.error || 'המחיקה נכשלה', 'error');
                    return false;
                }
                const dest = target && usage.alternatives.find(function (c) { return c.id === target; });
                window.showToast(dest
                    ? 'הקטגוריה נמחקה — ' + (usage.count === 1 ? 'העסקה הועברה' : usage.count + ' עסקאות הועברו')
                      + ' ל"' + dest.name + '"'
                    : 'הקטגוריה נמחקה');
                return true;
            });
        }).catch(function () {
            window.showToast(window.sfNetError(), 'error');
            return false;
        }).then(function (deleted) {
            deletingCategory = false;
            return deleted;
        });
    };

    yesBtn.addEventListener('click', function () { closeConfirm(true); });
    noBtn.addEventListener('click', function () { closeConfirm(false); });
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeConfirm(null);   // נסיגה, לא "לא"
    });

    // Escape סוגר, Tab/Shift+Tab נשארים בתוך הדיאלוג
    overlay.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { closeConfirm(null); return; }   // נסיגה
        if (e.key !== 'Tab') return;
        const focusables = withChoice ? [choiceEl, yesBtn, noBtn] : [yesBtn, noBtn];
        const idx = focusables.indexOf(document.activeElement);
        e.preventDefault();
        const next = e.shiftKey
            ? focusables[(idx <= 0 ? focusables.length : idx) - 1]
            : focusables[(idx + 1) % focusables.length];
        next.focus();
    });
})();



/* ─── רענון רך ────────────────────────────────────────────────────────────────
 *
 * כל פעולה באפליקציה הסתיימה ב-location.reload(). הוספת עסקה עלתה בערך שתי
 * שניות מהקשה עד מסך יציב: השהיה מכוונת של 380ms כדי שהצליל יסתיים, סבב
 * לשרת, ניתוח מחדש של 99KB CSS ו-77KB JS, ואז אנימציית ספירה של שנייה על
 * המספר שבדיוק רצית לראות. בדרך גם נמחקה השורה הזמנית שהקוד הספיק להציג,
 * וגם מיקום הגלילה.
 *
 * מושכים את אותה כתובת ומחליפים רק את מה שהשתנה. Jinja נשאר מקור האמת
 * היחיד — לא משכפלים כאן לוגיקת תצוגה, וזה מקור באגים שנמנע. הנפילה חזרה
 * ל-reload מלא אומרת שבמקרה הגרוע ההתנהגות זהה להיום.
 *
 * האנימציות לא רצות שוב בכוונה: ספירה מ-0 אחרי עדכון גורמת למספר
 * "לקפוץ אחורה" מול העיניים, וה-HTML הטרי ממילא מכיל כבר את הערך הסופי.
 */
/* אזורי העמוד שהרענון הרך מחליף.
 *
 * ה-hero הוא **אח** של ‎main‎ ב-base.html, לא בן — אז רענון שהחליף רק
 * את ‎main‎ השאיר את "נשאר בעו״ש החודש" תקוע אחרי כל הוספה ועריכה.
 * זה המספר שכל האפליקציה קיימת בשבילו.
 *
 * ולמשפחה חדשה זה היה גרוע במיוחד: ה-hero מציג "לחצו על + כדי להוסיף
 * את העסקה הראשונה שלכם ולראות כאן את היתרה שלכם", והמשפט הזה נשאר
 * על המסך מעל העסקה שהרגע נוספה. */
const SF_RELOAD_REGIONS = ['header.page-hero', 'main.main-content'];

/* ‎pendingToast‎: הודעה שהקורא מתכוון להציג אחרי הרענון. אם הרענון הרך לא
 * מתאפשר ונופלים לרענון מלא, היא נשמרת כדי שתוצג אחרי הטעינה ולא תאבד —
 * ואז ההבטחה מחזירה ‎'reloaded'‎, כדי שהקורא לא יציג אותה פעמיים. */
window.softReload = function (selector, pendingToast) {
    const regions = selector ? [selector] : SF_RELOAD_REGIONS;
    function fullReload() {
        if (pendingToast) window.sfToastAfterReload(pendingToast);
        window.location.reload();
        return 'reloaded';
    }
    return fetch(window.location.href, {
        headers: { 'X-Requested-With': 'sf-soft-reload' },
        credentials: 'same-origin',
    })
        .then(function (r) {
            // 401 כבר מטופל ב-auth-guard; כל דבר אחר — נופלים לרענון מלא
            if (!r.ok) throw new Error('soft reload got ' + r.status);
            return r.text();
        })
        .then(function (html) {
            const doc = new DOMParser().parseFromString(html, 'text/html');

            // חודש שהיה ריק לא טוען את ספריית הגרפים (70KB שאין מה לצייר
            // בהם). אחרי העסקה הראשונה ה-HTML החדש כבר מביא גרפים — ובלי
            // הספרייה הם נשארו ריבועים ריקים. פעם אחת בחודש: רענון מלא.
            if (typeof window.Chart === 'undefined' && doc.querySelector('main canvas')) {
                return fullReload();
            }

            // כל האזורים נאספים לפני שנוגעים באחד מהם: החלפה חלקית —
            // hero חדש מעל גוף ישן — גרועה מרענון מלא.
            const pairs = regions.map(function (sel) {
                return [document.querySelector(sel), doc.querySelector(sel)];
            });
            if (pairs.some(p => !p[0] || !p[1])) throw new Error('missing region');

            // אלמנטים שמחזיקים מצב משלהם (‎data-sf-keep‎ — באנר ההתקנה) עוברים
            // כמו שהם אל התוכן החדש, במקום להתחלף בעותק ריק מהשרת
            const keep = [];
            pairs.forEach(function (pair) {
                if (pair[0].querySelectorAll) {
                    pair[0].querySelectorAll('[data-sf-keep][id]').forEach(function (el) { keep.push(el); });
                }
            });

            pairs.forEach(function (pair) { pair[0].replaceWith(pair[1]); });

            keep.forEach(function (el) {
                const fresh = document.getElementById(el.id);
                if (fresh && fresh !== el) fresh.replaceWith(el);
            });

            // בלוקי הנתונים של העמוד (‎sf-view-data‎ וכו') יושבים ב-‎{% block
            // scripts %}‎ — מחוץ לאזורים שהוחלפו. בלי זה הגרפים והמקרא של עמוד
            // החודש צוירו מחדש מהמספרים הישנים, מתחת לכרטיסים שכבר התעדכנו.
            doc.querySelectorAll('script[type="application/json"][id]').forEach(function (fresh) {
                const current = document.getElementById(fresh.id);
                if (current && current.tagName === 'SCRIPT') current.textContent = fresh.textContent;
            });
            // מודיעים למי שצריך לחבר את עצמו מחדש (אנימציות, גרפים)
            window.dispatchEvent(new CustomEvent('sf:refreshed'));
        })
        .catch(fullReload);
};


// ── "הפרויקט הסתיים" / "פתיחה מחדש" (מתן, 30.9 — סבב 6, פריט 3) ──
// הכפתור בעמוד העריכה ובפס של פרויקט שהסתיים. סיום שואל קודם; החזרה לא —
// היא לא מסתירה כלום.
document.addEventListener('click', function (e) {
    const btn = e.target.closest && e.target.closest('[data-archive-project]');
    if (!btn || btn.disabled) return;
    const archived = btn.dataset.archived === 'true';
    const ask = archived ? window.appConfirm({
        title: 'לסמן את "' + btn.dataset.name + '" כפרויקט שהסתיים?',
        message: 'הוא לא יופיע יותר בטופס ההוספה וברשימת הפרויקטים, אבל כל העסקאות '
               + 'והסכומים נשמרים, ואפשר להחזיר אותו בכל רגע.',
        confirmText: 'סיום הפרויקט',
        danger: false,
    }) : Promise.resolve(true);
    ask.then(function (ok) {
        if (!ok) return;
        btn.disabled = true;
        fetch('/api/projects/' + btn.dataset.archiveProject + '/archive', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ archived: archived }),
        })
            .then(function (r) {
                return r.json().catch(function () { return {}; }).then(function (d) {
                    if (!r.ok) throw new Error(d.error || 'HTTP ' + r.status);
                });
            })
            .then(function () {
                try {
                    window.sfToastAfterReload(archived ? 'הפרויקט סומן כפרויקט שהסתיים'
                                                       : 'הפרויקט נפתח מחדש');
                } catch (err) { /* בלי טוסט — לא בלי הרענון */ }
                window.location.reload();
            })
            .catch(function (err) {
                btn.disabled = false;
                window.showToast(err && err.message && !/^HTTP/.test(err.message)
                                 ? err.message : window.sfNetError(), 'error');
            });
    });
});


// ── "השבוע" בדף הבית: נגיעה ביום מציגה את העסקאות שלו (מתן, 30.9) ──
// בהאצלה — הכרטיס מתחלף ברענון רך
document.addEventListener('click', function (e) {
    const btn = e.target.closest && e.target.closest('.week-day');
    if (!btn || btn.disabled) return;
    const card = btn.closest('.week-card');
    card.querySelectorAll('.week-day').forEach(function (b) {
        const on = b === btn;
        b.classList.toggle('is-selected', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    card.querySelectorAll('.week-detail').forEach(function (d) {
        d.hidden = d.dataset.day !== btn.dataset.day;
    });
});


// ── "השבוע": דפדוף לשבועות קודמים — חצים והחלקה (מתן, 2.10) ──
// השרת מחזיר את הכרטיס כולו מאותה תבנית שדף הבית מרנדר; מחליפים אותו במקום.
// בהאצלה — רענון רך מחזיר את הכרטיס לשבוע הנוכחי, וזה בסדר.
(function () {
    let loading = false;

    // ‎dir‎: מאיזה צד הכרטיס יוצא בהחלקה (‎-1‎ שמאלה, ‎1‎ ימינה); בחצים — בלי
    function goToWeek(card, offset, focusSel, dir) {
        if (loading || offset < 0) return;
        loading = true;
        card.classList.add('is-loading');
        if (dir && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) dir = 0;
        if (dir) {
            card.style.transition = 'transform 0.18s ease-in';
            card.style.transform = 'translateX(' + (dir * 40) + 'px)';
        }
        fetch('/api/week?offset=' + offset, { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) throw new Error('week ' + r.status);
                return r.text();
            })
            .then(function (html) {
                const tpl = document.createElement('template');
                tpl.innerHTML = html.trim();
                const fresh = tpl.content.querySelector('.week-card');
                if (!fresh) throw new Error('no card');
                card.replaceWith(fresh);
                if (dir) {
                    // הכרטיס החדש נכנס מהצד השני
                    fresh.style.transform = 'translateX(' + (-dir * 40) + 'px)';
                    fresh.style.opacity = '0.6';
                    requestAnimationFrame(function () {
                        fresh.style.transition = 'transform 0.2s ease-out, opacity 0.2s';
                        fresh.style.transform = '';
                        fresh.style.opacity = '';
                        setTimeout(function () { fresh.style.transition = ''; }, 220);
                    });
                }
                // המיקוד נשאר על החץ שנלחץ — מקלדת וקורא מסך לא "נופלים" לראש העמוד
                const again = focusSel && fresh.querySelector(focusSel);
                if (again && !again.disabled) again.focus({ preventScroll: true });
            })
            .catch(function () {
                card.classList.remove('is-loading');
                settle(card);
                window.showToast(window.sfNetError(), 'error');
            })
            .then(function () { loading = false; });
    }

    document.addEventListener('click', function (e) {
        const btn = e.target.closest && e.target.closest('.week-nav-btn');
        if (!btn || btn.disabled) return;
        const card = btn.closest('.week-card');
        const older = Number(btn.dataset.weekGo) > Number(card.dataset.offset);
        goToWeek(card, Number(btn.dataset.weekGo),
                 older ? '.week-nav-btn[aria-label="שבוע קודם"]' : '.week-nav-btn[aria-label="שבוע הבא"]');
    });

    // החלקה: בעברית הזמן זורם מימין לשמאל (ראשון בימין), אז השבוע הקודם
    // "נמצא" מימין — גרירה שמאלה מביאה אותו, וגרירה ימינה חוזרת קדימה.
    //
    // נעילת כיוון (מתן, 2.10: "שאם אני גולל שם, זה לא יגלול לי את המסך"):
    // אחרי 8px מחליטים פעם אחת אם זו תנועה הצידה או גלילה. הצידה — המסך
    // ננעל עד שהאצבע עוזבת, והכרטיס זז איתה. גלילה — לא נוגעים בכלום.
    let sx = null, sy = 0, axis = null, drag = null;
    let samples = [];                  // מיקום וזמן, למהירות בעזיבה

    function canGo(card, older) {
        const b = card.querySelector('.week-nav-btn[aria-label="' + (older ? 'שבוע קודם' : 'שבוע הבא') + '"]');
        return !!(b && !b.disabled);
    }
    function settle(card) {
        card.style.transition = 'transform 0.2s ease-out';
        card.style.transform = '';
        setTimeout(function () { card.style.transition = ''; }, 220);
    }

    document.addEventListener('touchstart', function (e) {
        const card = e.target.closest && e.target.closest('.week-card');
        if (!card || loading || e.touches.length !== 1) { sx = null; return; }
        sx = e.touches[0].clientX; sy = e.touches[0].clientY;
        axis = null; drag = card;
        samples = [{ t: e.timeStamp, p: sx }];
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
        if (sx === null || !drag) return;
        const dx = e.touches[0].clientX - sx, dy = e.touches[0].clientY - sy;
        if (!axis) {
            if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
            axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
        }
        if (axis !== 'x') return;
        e.preventDefault();                       // המסך לא זז כל עוד מחליקים הצידה
        // מעבר שאי אפשר לעשות (אין שבוע הבא / אין ישן יותר) — התנגדות חזקה
        const allowed = canGo(drag, dx < 0);
        drag.style.transition = '';
        drag.style.transform = 'translateX(' + Math.round(dx * (allowed ? 0.45 : 0.12)) + 'px)';
        samples.push({ t: e.timeStamp, p: e.touches[0].clientX });
        if (samples.length > 6) samples.shift();
    }, { passive: false });

    document.addEventListener('touchend', function (e) {
        if (sx === null || !drag) return;
        const card = drag;
        const dx = e.changedTouches[0].clientX - sx;
        const wasX = axis === 'x';
        sx = null; drag = null; axis = null;
        if (!wasX) return;
        // לפי **לאן התנועה הולכת** ולא רק כמה זזה (מתן, 7.10 — בנוסח אפל):
        // הנפה קצרה ומהירה מעבירה שבוע, וגרירה ארוכה שחוזרת לאחור — לא
        const aim = dx + window.sfProject(window.sfVelocity(samples, e.timeStamp), 0.99);
        const older = aim < 0;
        // גרירה לצד אחד והנפה חזרה לצד השני — התחרטות, לא בקשה לשבוע ההפוך
        if (Math.abs(aim) < 50 || (aim < 0) !== (dx < 0) || !canGo(card, older)) { settle(card); return; }
        const offset = Number(card.dataset.offset);
        goToWeek(card, older ? offset + 1 : offset - 1, null, older ? -1 : 1);
    }, { passive: true });

    document.addEventListener('touchcancel', function () {
        if (drag) settle(drag);
        sx = null; drag = null; axis = null;
    }, { passive: true });
})();
