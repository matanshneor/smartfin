const SF_VIEW = window.sfData('sf-view-data');

/* ═══ האינטראקטיביות של העמוד ═══
 * לפני הגרפים ובנפרד מהם: פתיחת קטגוריה חייבת לעבוד גם בלי Chart.js. */
(function () {

// ── הרחבת קטגוריה: הצגת כל העסקאות שלה בפרויקט (כמו בעמוד החודש) ──
function toggleExpand(trigger) {
    const wrap = trigger.closest('.legend-item-wrap');
    if (!wrap) return;
    // המצב לפי ‎aria-expanded‎ ולא לפי המחלקה: בסגירה המחלקה נשארת עד סוף ההחלקה
    const isOpen = trigger.getAttribute('aria-expanded') !== 'true';
    trigger.setAttribute('aria-expanded', isOpen);
    const list = wrap.querySelector('.cat-tx-list');
    const apply = function (open) { wrap.classList.toggle('open', open); };
    if (list && window.sfReveal) window.sfReveal(list, isOpen, apply); else apply(isOpen);
}

document.addEventListener('click', function (e) {
    const trigger = e.target.closest('.legend-item.clickable');
    if (trigger) toggleExpand(trigger);
});

document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const trigger = e.target.closest('.legend-item.clickable');
    if (trigger) { e.preventDefault(); toggleExpand(trigger); }
});

})();


/* ═══ הגרפים ═══  (ראו chart-setup.js) */
(function () {
if (!window.sfCharts.ready) return;

const COLORS    = window.sfCharts.colors;
const breakdown = SF_VIEW.breakdown;
['expense', 'income', 'savings'].forEach(function (typ) {
    const items = breakdown[typ] || [];
    const ctx = document.getElementById('chart-' + typ);
    if (!ctx || !items.length) return;

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: items.map(d => d.name),
            datasets: [{
                data:            items.map(d => d.total),
                backgroundColor: COLORS.slice(0, items.length),
                borderColor:     window.sfCharts.surface,
                borderWidth:     2,
                borderRadius:    4,
                spacing:         2,
                hoverOffset:     6,
            }]
        },
        options: {
            cutout: '70%',
            plugins: {
                tooltip: {
                    callbacks: {
                        label: c => ` ₪${window.sfMoney(c.parsed)} (${items[c.dataIndex].pct}%)`
                    }
                }
            }
        }
    });
});
})();

/* "הצג את כל העסקאות" — בבלוק משלו ולא בתוך הגרפים: הבלוק שלהם יוצא מוקדם
 * כשאין Chart.js, והכפתור היה מת יחד איתו. בהאצלה, כי רענון רך מחליף אותו. */
(function () {
document.addEventListener('click', function (e) {
    const btn = e.target.closest('#showAllProjectTx');
    if (!btn) return;
    const list = document.getElementById('projectTxList');
    if (!list) return;
    const open = list.classList.toggle('show-all');
    btn.setAttribute('aria-expanded', String(open));
    btn.textContent = open ? btn.dataset.less : btn.dataset.more;
});
})();
