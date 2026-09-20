const SF_VIEW = window.sfData('sf-view-data');

// "לאן הלך הכסף": כל הכסף שיצא, והחלוקה בין הוצאות לחיסכון. בלי קשר
// להכנסות — זה מה שיצא, לא כמה נשאר. מחושב פעם אחת ברמת הקובץ כי גם
// המקרא וגם הדונאט צריכים בדיוק את אותה רשימה, והמקרא נבנה גם כשאין
// ספרייה לצייר בה.
const OVERVIEW_PARTS = [
    { label: 'הוצאות', value: (SF_VIEW.summary || {}).expense || 0, color: '#A04545' },
    { label: 'חיסכון', value: (SF_VIEW.summary || {}).savings || 0, color: '#A67C00' },
].filter(p => p.value > 0);
const OVERVIEW_TOTAL = OVERVIEW_PARTS.reduce((s, p) => s + p.value, 0);

// מרכוז החודש הנוכחי ברצועה בטעינה. ה"מגנט" עצמו כולו CSS — כאן רק
// ממקמים את נקודת ההתחלה.
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


/* ═══ האינטראקטיביות של העמוד ═══
 *
 * בלוק נפרד מהגרפים, ולפניהם, בכוונה: כל מה שכאן חייב לעבוד גם כשאין
 * Chart.js. עד עכשיו הכול ישב יחד, והשורה הראשונה של הגרפים הפילה את
 * השאר — כולל בחודש ריק, שבו התבנית בכלל לא טוענת את הספרייה.
 */
(function () {

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

// ── המקרא של "לאן הלך הכסף" ──
// נבנה כאן ולא עם הגרף: אלה המספרים עצמם (הוצאות מול חיסכון, בשקלים
// ובאחוזים), והם השווים ביותר בכרטיס. הדונאט רק מצייר אותם.
const legend = document.getElementById('overviewLegend');
if (legend && OVERVIEW_TOTAL > 0) {
    OVERVIEW_PARTS.forEach(p => {
        const li = document.createElement('li');
        li.className = 'legend-item';
        li.innerHTML = `
            <span class="legend-dot" style="background:${p.color}"></span>
            <span class="legend-name">${p.label}</span>
            <span class="legend-pct">${Math.round(p.value / OVERVIEW_TOTAL * 100)}%</span>
            <span class="legend-amount">₪${p.value.toLocaleString('en-US')}</span>`;
        legend.appendChild(li);
    });
}

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


/* ═══ הגרפים ═══  (ראו chart-setup.js) */
(function () {
if (!window.sfCharts.ready) return;

const COLORS    = window.sfCharts.colors;
const GRID_LINE = window.sfCharts.grid;

// ── 1. לאן הלך הכסף ──
const parts = OVERVIEW_PARTS;
if (parts.length) {
    const outTotal = OVERVIEW_TOTAL;
    const ctx = document.getElementById('overviewChart');
    if (ctx) {
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
SF_VIEW.members.forEach(function (mb) {
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

})();
