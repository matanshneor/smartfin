const SF_VIEW = window.sfData('sf-view-data');

(function () {
const COLORS = [
    '#A67C00','#3D6B54','#A04545','#44609B',
    '#75588F','#3E7373','#9C6A3C','#8F5470'
];
Chart.defaults.font.family = "'Rubik', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
Chart.defaults.color = '#78716C';
Chart.defaults.animation.duration = 900;
Chart.defaults.animation.easing = 'easeOutQuart';
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#1C1917';
Chart.defaults.plugins.tooltip.titleColor = '#FAF7F0';
Chart.defaults.plugins.tooltip.bodyColor = '#E7E0D2';

// צבעי הגרף זמינים גם ל-CSS — הנקודות במקרא מרונדרות בשרת
COLORS.forEach((c, i) =>
    document.documentElement.style.setProperty('--chart-color-' + i, c));

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
