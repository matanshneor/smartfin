const SF_VIEW = window.sfData('sf-view-data');

// מרכוז החודש הנוכחי ברצועה בטעינה. ה"מגנט" עצמו כולו CSS — כאן רק
// ממקמים את נקודת ההתחלה. בלוק נפרד ולפני Chart.js בכוונה: גם אם ה-CDN
// לא נענה, הרצועה עדיין תיפתח במקום הנכון.
(function () {
const strip = document.getElementById('monthStrip');
if (!strip) return;
const active = strip.querySelector('.month-chip.is-current');
if (!active) return;
// ללא אנימציה — קפיצה לגלילה חלקה בטעינת עמוד נראית כמו תקלה
const prev = strip.style.scrollBehavior;
strip.style.scrollBehavior = 'auto';
strip.scrollLeft += active.getBoundingClientRect().left + active.offsetWidth / 2
                  - (strip.getBoundingClientRect().left + strip.offsetWidth / 2);
strip.style.scrollBehavior = prev;
})();


(function () {
const COLORS = [
    '#A67C00','#3D6B54','#A04545','#44609B',
    '#75588F','#3E7373','#9C6A3C','#8F5470'
];
const TEXT_MUTED = '#78716C';
const GRID_LINE  = 'rgba(28,25,23,0.07)';

Chart.defaults.font.family = "'Rubik', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
Chart.defaults.color = TEXT_MUTED;
Chart.defaults.animation.duration = 900;
Chart.defaults.animation.easing = 'easeOutQuart';
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#1C1917';
Chart.defaults.plugins.tooltip.titleColor = '#FAF7F0';
Chart.defaults.plugins.tooltip.bodyColor = '#E7E0D2';

COLORS.forEach((c, i) =>
    document.documentElement.style.setProperty('--chart-color-' + i, c));

// ── הרחבת קטגוריה: הצגת כל העסקאות שלה בחודש ──
function toggleExpand(trigger) {
    const wrap = trigger.classList.contains('breakdown-main')
        ? trigger.closest('.breakdown-bar-row')
        : trigger.closest('.legend-item-wrap');
    if (!wrap) return;
    const isOpen = wrap.classList.toggle('open');
    trigger.setAttribute('aria-expanded', isOpen);
}

document.addEventListener('click', function (e) {
    const trigger = e.target.closest('.legend-item.clickable, .breakdown-main.clickable');
    if (trigger) toggleExpand(trigger);
});

document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const trigger = e.target.closest('.legend-item.clickable, .breakdown-main.clickable');
    if (trigger) { e.preventDefault(); toggleExpand(trigger); }
});

// ── הצגת/הסתרת קטגוריות ללא פעילות ──
document.addEventListener('click', function (e) {
    const toggle = e.target.closest('.zero-toggle');
    if (!toggle) return;
    const shown = toggle.parentElement.classList.toggle('show-zeros');
    toggle.classList.toggle('open', shown);
});

const summary = SF_VIEW.summary;

// ── 1. לאן הלך הכסף: כל הכסף שיצא (הוצאות + חיסכון) והחלוקה ביניהם ──
// בלי קשר להכנסות — הגרף מציג מה יצא, לא כמה נשאר.
const outTotal = summary.expense + summary.savings;
if (outTotal > 0) {
    const ctx = document.getElementById('overviewChart');
    const parts = [
        { label: 'הוצאות', value: summary.expense, color: '#A04545' },
        { label: 'חיסכון', value: summary.savings, color: '#A67C00' },
    ].filter(p => p.value > 0);

    if (ctx && parts.length) {
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: parts.map(p => p.label),
                datasets: [{
                    data:            parts.map(p => p.value),
                    backgroundColor: parts.map(p => p.color),
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
                            label: c => ` ${c.label}: ₪${c.parsed.toLocaleString('en-US')} (${Math.round(c.parsed / outTotal * 100)}%)`
                        }
                    }
                }
            }
        });

        const legend = document.getElementById('overviewLegend');
        parts.forEach(p => {
            const li = document.createElement('li');
            li.className = 'legend-item';
            li.innerHTML = `
                <span class="legend-dot" style="background:${p.color}"></span>
                <span class="legend-name">${p.label}</span>
                <span class="legend-pct">${Math.round(p.value / outTotal * 100)}%</span>
                <span class="legend-amount">₪${p.value.toLocaleString('en-US')}</span>`;
            legend.appendChild(li);
        });
    }
}

// ── 2. הוצאות לפי קטגוריה ──
const expenseData = SF_VIEW.expense;
if (expenseData.length > 0) {
    const ctx = document.getElementById('expenseChart');
    if (ctx) {
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: expenseData.map(d => d.name),
                datasets: [{
                    data:            expenseData.map(d => d.total),
                    backgroundColor: COLORS.slice(0, expenseData.length),
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
                            label: c => ` ₪${c.parsed.toLocaleString('en-US')} (${expenseData[c.dataIndex].pct}%)`
                        }
                    }
                }
            }
        });
    }
}

// ── 5. חלוקה בין בני המשפחה — גרף נפרד לכל סוג שהמשפחה הפעילה בו שיוך ──
const membersData = SF_VIEW.members;
membersData.forEach(function (mb) {
    const ctx = document.getElementById('membersChart-' + mb.type);
    if (!ctx || !mb.rows.length) return;
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: mb.rows.map(m => m.name),
            datasets: [{
                label:           mb.label,
                data:            mb.rows.map(m => m.expense),
                // צבע קבוע לכל בן משפחה — זהה לצבע תג-השם שלו (ראה app.py)
                backgroundColor: mb.rows.map(m => m.color),
                borderRadius:    6,
                maxBarThickness: 64,
            }]
        },
        options: {
            responsive:          true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: c => ` ${mb.label}: ₪${c.parsed.y.toLocaleString('en-US')}`
                    }
                }
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 12 } } },
                y: {
                    grid: { color: GRID_LINE },
                    ticks: { font: { size: 11 }, callback: v => '₪' + v.toLocaleString('en-US') }
                }
            }
        }
    });
});

// ── חיפוש/סינון ברשימת "כל העסקאות" (client-side) ──
const txSearch = document.getElementById('txSearch');
if (txSearch) {
    const allRows = Array.from(document.querySelectorAll('.all-tx-header + .tx-search-wrap + .cat-tx-list .cat-tx-row'));
    const emptyMsg = document.getElementById('txSearchEmpty');
    txSearch.addEventListener('input', function () {
        const q = txSearch.value.trim().toLowerCase();
        let shown = 0;
        allRows.forEach(function (row) {
            const desc = (row.querySelector('.cat-tx-desc') || {}).textContent || '';
            const match = !q || desc.toLowerCase().indexOf(q) !== -1;
            row.style.display = match ? '' : 'none';
            if (match) shown++;
        });
        emptyMsg.style.display = (q && shown === 0) ? 'block' : 'none';
    });
}
})();
