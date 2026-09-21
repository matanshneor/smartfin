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
            const format = v => prefix + '₪' + Math.round(v).toLocaleString('en-US');

            const key  = keyFor(el, seen);
            const prev = lastShown[key];
            lastShown[key] = { value: target, prefix: prefix };

            // מאיפה מתחילים. היפוך סימן (עודף ↔ גירעון) מתחיל מ-0:
            // המספר מוצג בערך מוחלט, ומעבר ישיר בין שני ערכים מוחלטים
            // היה מציג סכומי ביניים עם הסימן ההפוך.
            const from = (prev && prev.prefix === prefix) ? prev.value : 0;

            if (reduceMotion || from === target) {
                el.textContent = format(target);
                return;
            }

            const duration = 1000;
            const start = performance.now();
            function tick(now) {
                const p = Math.min((now - start) / duration, 1);
                const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
                el.textContent = format(from + (target - from) * eased);
                if (p < 1) requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        });
    }

    // 2. Stagger: כרטיסים נכנסים בהדרגה
    function runStagger() {
        if (reduceMotion) return;
        const items = document.querySelectorAll(
            '.summary-card, .chart-card, .transaction-item, .settings-card, ' +
            '.month-item, .alert-card, .kpi-card, .empty-state'
        );
        items.forEach(function (el, i) {
            el.style.animationDelay = Math.min(i * 55, 600) + 'ms';
            el.classList.add('anim-rise');
        });
    }

    // 3. פסי התקדמות נמתחים מ-0 לרוחב הסופי
    function runBars() {
        if (reduceMotion) return;
        document.querySelectorAll('.balance-bar-fill, .breakdown-fill')
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
    });
})();
