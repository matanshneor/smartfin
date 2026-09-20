const SF_VIEW = window.sfData('sf-view-data');

/* ═══ האינטראקטיביות של העמוד ═══
 * לפני הגרפים ובנפרד מהם: פתיחת קטגוריה חייבת לעבוד גם בלי Chart.js. */
(function () {

// ── הרחבת קטגוריה: הצגת כל העסקאות שלה בפרויקט (כמו בעמוד החודש) ──
function toggleExpand(trigger) {
    const wrap = trigger.closest('.legend-item-wrap');
    if (!wrap) return;
    const isOpen = wrap.classList.toggle('open');
    trigger.setAttribute('aria-expanded', isOpen);
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
                borderColor:     '#FFFFFF',
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
                        label: c => ` ₪${c.parsed.toLocaleString('en-US')} (${items[c.dataIndex].pct}%)`
                    }
                }
            }
        }
    });
});
})();
