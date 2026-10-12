// אנימציות עדינות: ספירה עולה של מספרים, בכבוד ל-prefers-reduced-motion.
(function () {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* מה הוצג בפעם הקודמת, לכל מספר בעמוד.
     *
     * הרענון הרך מחליף את האלמנטים עצמם, אז אי אפשר לשמור את הערך
     * עליהם — הזיכרון הזה חי מחוץ ל-DOM. המפתח נגזר מהמחלקות ומהמיקום
     * בקבוצה, ולא ממזהה בתבנית, כדי שזה יעבוד בלי לגעת בכל מספר. */
    const lastShown = {};

    function keyFor(el, seen) {
        const base = el.className || 'countup';
        seen[base] = (seen[base] || 0) + 1;
        return base + '#' + seen[base];
    }

    /* Count-up: מהערך שהוצג קודם אל החדש.
     *
     * קודם זה תמיד רץ מ-0, וזה בזבז את כל הערך של האנימציה: אחרי
     * הוצאה של ₪100 ראית מספר מטפס מאפס, במקום לראות את מה שבאמת
     * קרה — שהיתרה ירדה ב-₪100. בטעינה ראשונה אין ערך קודם, ושם 0
     * הוא הנכון: זה הרושם הראשון, לא עדכון. */
    function runCountUps() {
        const seen = {};
        document.querySelectorAll('[data-countup]').forEach(function (el) {
            const target = parseFloat(el.dataset.countup);
            if (isNaN(target)) return;
            const prefix = el.dataset.prefix || '';
            // הספירה עצמה בשקלים שלמים תמיד, ורק הערך הסופי כמו שהוא — עם
            // אגורות אם יש לו. מתן (30.9): "הכסף נספר באגורות ואז מוצג מעוגל",
            // ו"שאנימציית הספירה תהיה בלי אגורות גם". ערכי הביניים שבורים
            // (‎1,203.57‎), ו-‎sfMoney‎ מציג אגורות כשיש — אז הן הבהבו לאורך הספירה.
            const step  = v => prefix + '₪' + window.sfMoney(Math.round(v));
            const final = prefix + '₪' + window.sfMoney(target);

            const key  = keyFor(el, seen);
            const prev = lastShown[key];
            lastShown[key] = { value: target, prefix: prefix };

            // מאיפה מתחילים. היפוך סימן (עודף ↔ גירעון) מתחיל מ-0:
            // המספר מוצג בערך מוחלט, ומעבר ישיר בין שני ערכים מוחלטים
            // היה מציג סכומי ביניים עם הסימן ההפוך.
            const from = (prev && prev.prefix === prefix) ? prev.value : 0;

            if (reduceMotion || from === target) {
                el.textContent = final;
                return;
            }

            const duration = 1000;
            const start = performance.now();
            function tick(now) {
                const p = Math.min((now - start) / duration, 1);
                const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
                el.textContent = p < 1 ? step(from + (target - from) * eased) : final;
                if (p < 1) requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        });
    }

    /* 2. כניסה של כרטיסים.
     *
     * מה שעל המסך בטעינה — נכנס בהדרגה (stagger), כמו תמיד. מה שמתחתיו נכנס
     * **עם הגלילה** (מתן, 11.10 — "שמה שנכנס יתחיל להיכנס לאט עם הגלילה"):
     * עד אז גם הכרטיסים שמתחת למסך "נכנסו" בטעינה, כשאיש לא ראה, ובגלילה
     * אליהם הם פשוט עמדו שם.
     *
     * הכניסה צמודה למיקום הגלילה ולא לזמן: מהיר — מהר, איטי — לאט, עצירה —
     * עוצרת, וגלילה חזרה מחזירה. בדפדפן שתומך (‎animation-timeline: view()‎,
     * ספארי 26 וכרום) זה CSS בלבד, בלי JS בזמן הגלילה. בדפדפן ישן — כניסה
     * רכה ברגע שהכרטיס מופיע (‎IntersectionObserver‎). */
    const REVEAL = '.summary-cards, .chart-card, .transaction-item, .settings-card, ' +
                   '.month-item, .alert-card, .kpi-card, .empty-state, .settings-group, ' +
                   '.empty-row, .project-tile';
    const scrollTimeline = !!(window.CSS && CSS.supports && CSS.supports('animation-timeline: view()'));
    let revealObserver = null;

    function belowTheFold(el) { return el.getBoundingClientRect().top > window.innerHeight - 40; }

    function setupReveal(els) {
        if (reduceMotion) return;
        els.forEach(function (el) {
            if (el.classList.contains('reveal-scroll') || el.classList.contains('reveal-fallback')) return;
            if (!belowTheFold(el)) return;
            if (scrollTimeline) { el.classList.add('reveal-scroll'); return; }
            if (!('IntersectionObserver' in window)) return;
            if (!revealObserver) {
                revealObserver = new IntersectionObserver(function (entries) {
                    entries.forEach(function (en) {
                        if (!en.isIntersecting) return;
                        en.target.classList.add('is-in');
                        revealObserver.unobserve(en.target);
                    });
                }, { rootMargin: '0px 0px -60px 0px', threshold: 0.05 });
            }
            el.classList.add('reveal-fallback');
            revealObserver.observe(el);
        });
    }

    function runStagger() {
        if (reduceMotion) return;
        const all = Array.prototype.slice.call(document.querySelectorAll(REVEAL));
        const below = all.filter(belowTheFold);
        // רק מה שהיה ברשימת הכניסה המקורית ונראה עכשיו — כמו קודם
        const items = all.filter(function (el) {
            return below.indexOf(el) === -1 && !el.matches('.settings-group, .empty-row, .project-tile');
        });
        setupReveal(below);
        items.forEach(function (el, i) {
            el.style.animationDelay = Math.min(i * 55, 600) + 'ms';
            el.classList.add('anim-rise');
            // בסוף הכניסה משחררים את הכרטיס. אנימציה שנגמרה עם ‎forwards‎
            // ממשיכה "להחזיק" את ‎transform‎, וגוברת על מה שהחלקה כותבת לו —
            // כרטיס "השבוע" לא זז עם האצבע בהחלקה הראשונה (מתן, 11.10).
            el.addEventListener('animationend', function done(e) {
                if (e.target !== el || e.animationName !== 'rise-in') return;
                el.removeEventListener('animationend', done);
                el.classList.remove('anim-rise');
                el.style.animationDelay = '';
            });
        });
    }

    // 3. פסי התקדמות נמתחים מ-0 לרוחב הסופי
    function runBars() {
        if (reduceMotion) return;
        document.querySelectorAll('.balance-bar-fill')
            .forEach(function (bar) {
                const finalWidth = bar.style.width;
                if (!finalWidth) return;
                bar.style.width = '0%';
                requestAnimationFrame(function () {
                    requestAnimationFrame(function () {
                        bar.style.width = finalWidth;
                    });
                });
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        runCountUps();
        runStagger();
        runBars();
    });

    /* אחרי רענון רך המספרים הוחלפו באלמנטים חדשים, וה-count-up צריך
     * לרוץ עליהם — דווקא אז הוא הכי שווה, כי זה הרגע שבו המשתמש מחכה
     * לראות את המספר החדש.
     *
     * ‎runStagger‎ במכוון לא: אנימציית כניסה שייכת לכניסה לעמוד, ולא
     * לעדכון במקום. כל הכרטיסים נכנסים מחדש בכל הוספת עסקה זה רעש. */
    window.addEventListener('sf:refreshed', function () {
        runCountUps();
        runBars();
        // תוכן חדש (רענון רך, מעבר חודש) — מה שמתחת למסך נכנס עם הגלילה
        setupReveal(Array.prototype.slice.call(document.querySelectorAll(REVEAL)));
    });
})();
