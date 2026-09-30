/* שלד טעינה (מתן, 30.9 — סבב 6, פריט 14).
 *
 * המעבר בין העמודים הוא טעינה מלאה. ברשת איטית (רכבת, מעלית) הלחיצה לא
 * עשתה שום דבר נראה עד שהעמוד הבא הגיע — ולא היה ברור אם היא נקלטה. עכשיו,
 * אם אחרי רבע שנייה עוד לא עזבנו, מופיע שלד בצורת העמוד שאליו הולכים.
 * ברשת מהירה הוא לא מופיע בכלל — שלא יהבהב סתם.
 *
 * זה לא מאיץ כלום. זה אומר "קיבלתי, בדרך". */
(function () {
    const DELAY = 250;
    let timer = null, overlay = null;

    // הצורה לפי העמוד: [כמה ריבועים בשורה העליונה, ואחריהם גבהים של כרטיסים]
    const SHAPES = {
        '/':         { chips: 3, blocks: [110, 64, 64, 64] },
        '/month':    { chips: 3, blocks: [230, 230, 120] },
        '/months':   { chips: 0, blocks: [260, 200, 180] },
        '/projects': { chips: 0, blocks: [72, 72, 72] },
        '/settings': { chips: 0, blocks: [60, 60, 60, 60, 60, 60] },
    };

    function build(shape) {
        const el = document.createElement('div');
        el.className = 'skeleton-screen';
        el.setAttribute('aria-hidden', 'true');
        const hero = document.createElement('div');
        hero.className = 'skeleton-hero';
        hero.innerHTML = '<span class="sk sk-line" style="width:38%"></span>'
                       + '<span class="sk sk-line sk-big" style="width:52%"></span>';
        el.appendChild(hero);
        const body = document.createElement('div');
        body.className = 'skeleton-body';
        if (shape.chips) {
            const row = document.createElement('div');
            row.className = 'skeleton-chips';
            for (let i = 0; i < shape.chips; i++) row.appendChild(Object.assign(document.createElement('span'), { className: 'sk sk-card' }));
            body.appendChild(row);
        }
        shape.blocks.forEach(function (h) {
            const b = document.createElement('span');
            b.className = 'sk sk-card';
            b.style.height = h + 'px';
            body.appendChild(b);
        });
        el.appendChild(body);
        return el;
    }

    function hide() {
        clearTimeout(timer);
        timer = null;
        if (overlay) { overlay.remove(); overlay = null; }
    }

    document.addEventListener('click', function (e) {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        const a = e.target.closest && e.target.closest('a[href]');
        if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
        const url = new URL(a.href, location.href);
        if (url.origin !== location.origin) return;
        if (url.pathname === location.pathname && url.search === location.search) return;   // רק עוגן באותו עמוד
        const shape = SHAPES[url.pathname] || (url.pathname.indexOf('/projects/') === 0 ? SHAPES['/month'] : null);
        if (!shape) return;
        hide();
        timer = setTimeout(function () {
            // קוד אחר ביטל את המעבר אחרי שקיבלנו את הלחיצה — אין לאן לחכות,
            // ושלד שהיה מופיע כאן לא היה נעלם לעולם
            if (e.defaultPrevented) return;
            overlay = build(shape);
            document.body.appendChild(overlay);
            // הלשונית שנלחצה בתפריט התחתון כבר מסומנת — "קיבלתי, בדרך לשם"
            if (a.closest('.bottom-nav')) {
                a.closest('.bottom-nav').querySelectorAll('.nav-item').forEach(function (n) {
                    n.classList.toggle('active', n === a);
                });
            }
        }, DELAY);
    });
    // חזרה אחורה מהמטמון של הדפדפן — העמוד חוזר כמו שהיה, עם השלד מעליו
    window.addEventListener('pageshow', hide);
    window.addEventListener('pagehide', function () { clearTimeout(timer); });
})();
