const SF_VIEW = window.sfData('sf-view-data');

/* ═══ הגרף ═══  (ראו chart-setup.js)
 * בלוק נפרד מ"הצג עוד" שלמטה: כשהספרייה לא נטענת, הכפתור עדיין עובד. */
(function () {
if (!window.sfCharts.ready) return;

const TEXT_MUTED = window.sfCharts.muted;
const GRID_LINE  = window.sfCharts.grid;

const trendData = SF_VIEW.trend;
const SHORT_MONTHS = ['', 'ינו׳', 'פבר׳', 'מרץ', 'אפר׳', 'מאי', 'יוני', 'יולי', 'אוג׳', 'ספט׳', 'אוק׳', 'נוב׳', 'דצמ׳'];

// ── השוואת חודשים ──
if (trendData.length > 0) {
    const last6 = trendData.slice(-6);
    const ctx = document.getElementById('compareChart');
    if (ctx) {
        new Chart(ctx, {
            type: 'bar',
            data: {
                // שמות מקוצרים מתחת לעמודות: בגופן 13 המלאים נדבקו זה לזה
                // ("אוגוסטספטמבר"). השם המלא — בחלונית כשנוגעים בעמודה.
                labels: last6.map(d => SHORT_MONTHS[d.month] || d.month_name),
                // בסדר הפוך: Chart.js מסדר את העמודות בכל חודש משמאל לימין, וכך
                // ההכנסות יוצאות מימין — כמו במקרא ובקריאה בעברית
                datasets: [
                    {
                        label:           'חיסכון',
                        data:            last6.map(d => d.savings),
                        backgroundColor: 'rgba(166,124,0,0.9)',
                        borderRadius:    5,
                        categoryPercentage: 0.86,   // עמודות רחבות, פחות רווח בין החודשים
                        barPercentage:      0.92,
                    },
                    {
                        label:           'הוצאות',
                        data:            last6.map(d => d.expense),
                        backgroundColor: 'rgba(160,69,69,0.9)',
                        borderRadius:    5,
                        categoryPercentage: 0.86,   // עמודות רחבות, פחות רווח בין החודשים
                        barPercentage:      0.92,
                    },
                    {
                        label:           'הכנסות',
                        data:            last6.map(d => d.income),
                        backgroundColor: 'rgba(61,107,84,0.9)',
                        borderRadius:    5,
                        categoryPercentage: 0.86,   // עמודות רחבות, פחות רווח בין החודשים
                        barPercentage:      0.92,
                    }
                ]
            },
            options: {
                responsive:          true,
                maintainAspectRatio: false,
                // נגיעה בחודש בגרף פותחת אותו, כמו שורה בטבלה (מתן, 30.9 — רעיון 10).
                // לפי העמודה כולה ולא רק העמודה שנפגעה: חיסכון של ₪0 אין בו
                // מה לפגוע, והאצבע רחבה מעמודה אחת
                onClick: function (evt, _els, chart) {
                    const hit = chart.getElementsAtEventForMode(evt, 'index', { intersect: false }, true);
                    if (!hit.length) return;
                    const d = last6[hit[0].index];
                    window.location.href = '/month?year=' + d.year + '&month=' + d.month;
                },
                onHover: function (evt, els) {
                    evt.native.target.style.cursor = els.length ? 'pointer' : 'default';
                },
                plugins: {
                    legend: {
                        display:  true,
                        position: 'bottom',
                        labels: { boxWidth: 14, padding: 18, font: { size: 14 }, color: TEXT_MUTED }
                    },
                    tooltip: {
                        callbacks: {
                            title: items => last6[items[0].dataIndex].month_name,
                            label: c => ` ${c.dataset.label}: ₪${window.sfMoney(c.parsed.y)}`
                        }
                    }
                },
                // מימין לשמאל (מתן, 30.9): החודש הישן בימין והחדש בשמאל, כמו
                // שקוראים בעברית, והסולם של הסכומים בצד ימין
                scales: {
                    x: { reverse: true, grid: { display: false },
                         // שמות ישרים ולא מוטים — המוטה נחתך בקצה
                         ticks: { font: { size: 13 }, maxRotation: 0, autoSkip: false } },
                    y: {
                        position: 'right',
                        grid: { color: GRID_LINE },
                        ticks: { font: { size: 13 }, callback: v => '₪' + v.toLocaleString('en-US') }
                    }
                }
            }
        });
    }
}

// ── לפי קטגוריה (מתן, 30.9) ──
// אותם חודשים כמו הגרף שמעל, מימין לשמאל כמו הוא. הסכום מעל כל עמודה, קו
// מקווקו בגובה הממוצע, והחודש הנוכחי בהיר יותר — הוא עוד לא נגמר.
const catTrend = SF_VIEW.cat_trend;
const catCanvas = document.getElementById('categoryChart');
if (catTrend && catTrend.categories.length && catCanvas) {
    const months = catTrend.months;
    const money = v => '₪' + window.sfMoney(Math.round(v));
    const isNow = months.length && (function () {
        const d = new Date(), last = months[months.length - 1];
        return last.year === d.getFullYear() && last.month === d.getMonth() + 1;
    })();
    const BAR = 'rgba(160,69,69,0.9)', BAR_NOW = 'rgba(160,69,69,0.35)';

    // הסכום מעל כל עמודה — בלי תוסף: שורה אחת שמציירת אחרי העמודות
    const valuesOnTop = {
        id: 'sfValuesOnTop',
        afterDatasetsDraw: function (chart) {
            const ctx = chart.ctx, meta = chart.getDatasetMeta(0);
            ctx.save();
            ctx.fillStyle = TEXT_MUTED;
            ctx.font = '600 12px ' + getComputedStyle(document.body).fontFamily;
            ctx.textAlign = 'center';
            meta.data.forEach(function (bar, i) {
                const v = chart.data.datasets[0].data[i];
                if (v > 0) ctx.fillText(Math.round(v).toLocaleString('en-US'), bar.x, bar.y - 6);
            });
            ctx.restore();
        },
    };

    const chart = new Chart(catCanvas, {
        type: 'bar',
        data: {
            labels: months.map(m => m.label),
            datasets: [
                { label: 'הוצאה', data: [], borderRadius: 5,
                  backgroundColor: months.map((m, i) => (isNow && i === months.length - 1) ? BAR_NOW : BAR),
                  categoryPercentage: 0.86, barPercentage: 0.8, order: 2 },
                { type: 'line', label: 'ממוצע', data: [], borderColor: TEXT_MUTED, borderWidth: 1.2,
                  borderDash: [4, 4], pointRadius: 0, pointHitRadius: 0, fill: false, order: 1 },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 20 } },
            plugins: {
                legend: { display: false },
                tooltip: {
                    filter: item => item.datasetIndex === 0,
                    callbacks: {
                        title: items => months[items[0].dataIndex].name,
                        label: c => ' ' + money(c.parsed.y),
                    },
                },
            },
            scales: {
                x: { reverse: true, grid: { display: false },
                     ticks: { font: { size: 13 }, maxRotation: 0, autoSkip: false } },
                y: { display: false, beginAtZero: true, grid: { display: false } },
            },
        },
        plugins: [valuesOnTop],
    });

    // ── נגיעה בעמודה של חודש: חלון עם ההוצאות של הקטגוריה באותו חודש (מתן, 30.9) ──
    let sheet = null;
    function closeSheet() {
        if (sheet) { sheet.remove(); sheet = null; }
        catCanvas.focus && catCanvas.focus({ preventScroll: true });
    }
    function openMonth(i) {
        if (!current) return;
        const m = months[i];
        const items = (current.items || [])[i] || [];
        if (sheet) sheet.remove();
        sheet = document.createElement('div');
        sheet.className = 'color-sheet cat-month-sheet';
        sheet.setAttribute('role', 'dialog');
        sheet.setAttribute('aria-modal', 'true');
        sheet.setAttribute('aria-labelledby', 'catMonthTitle');
        const card = document.createElement('div');
        card.className = 'color-sheet-card';
        const title = document.createElement('p');
        title.className = 'color-sheet-title';
        title.id = 'catMonthTitle';
        title.textContent = current.icon + ' ' + current.name + ' · ' + m.name + ' ' + m.year;
        const sub = document.createElement('p');
        sub.className = 'color-sheet-hint';
        sub.textContent = items.length
            ? window.sfCount(items.length, 'עסקה אחת', 'עסקאות') + ' · ' + money(current.values[i])
            : 'לא בוצעו עסקאות בקטגוריה בחודש זה';
        card.append(title, sub);
        if (items.length) {
            const ul = document.createElement('ul');
            ul.className = 'cat-month-list';
            items.forEach(function (t) {
                const li = document.createElement('li');
                const d = document.createElement('span');
                d.className = 'cat-month-date';
                d.textContent = t.date.slice(8, 10) + '.' + t.date.slice(5, 7);
                const n = document.createElement('span');
                n.className = 'cat-month-desc';
                n.textContent = t.description || current.name;
                const a = document.createElement('span');
                a.className = 'cat-month-amount';
                a.textContent = '-' + money(t.amount);
                li.append(d, n, a);
                ul.appendChild(li);
            });
            card.appendChild(ul);
        }
        const actions = document.createElement('div');
        actions.className = 'edit-actions';
        const link = document.createElement('a');
        link.className = 'btn-sm btn-ghost';
        link.href = '/month?year=' + m.year + '&month=' + m.month + '#expense-breakdown';
        link.textContent = 'לעמוד החודש';
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'btn-sm btn-primary';
        close.textContent = 'סגירה';
        close.addEventListener('click', closeSheet);
        actions.append(close, link);
        card.appendChild(actions);
        sheet.appendChild(card);
        sheet.addEventListener('click', function (e) { if (e.target === sheet) closeSheet(); });
        document.body.appendChild(sheet);
        close.focus({ preventScroll: true });
    }
    // לפי העמודה כולה, כמו בגרף שמעל — גם חודש בלי הוצאה נפתח ואומר את זה
    chart.options.onClick = function (evt) {
        const hit = chart.getElementsAtEventForMode(evt, 'index', { intersect: false }, true);
        if (hit.length) openMonth(hit[0].index);
    };
    chart.options.onHover = function (evt, els) {
        evt.native.target.style.cursor = els.length ? 'pointer' : 'default';
    };
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sheet) closeSheet();
    });

    const stats = document.getElementById('catTrendStats');
    let current = null;
    function show(key) {
        const c = catTrend.categories.find(x => x.key === key) || catTrend.categories[0];
        current = c;
        chart.data.datasets[0].data = c.values;
        // קו הממוצע לכל רוחב הגרף; בלי חודש שנגמר — אין ממוצע
        chart.data.datasets[1].data = c.avg == null ? [] : c.values.map(() => c.avg);
        chart.options.scales.y.suggestedMax = Math.max.apply(null, c.values) * 1.12;
        chart.update();
        const cell = (label, value) => '<div>' + label + '<b>' + value + '</b></div>';
        stats.innerHTML =
            cell('ממוצע לחודש', c.avg == null ? '—' : '<span class="num">' + money(c.avg) + '</span>') +
            cell('הכי יקר' + (c.max_label ? ' · ' + c.max_label : ''),
                 c.max_label ? '<span class="num">' + money(c.max) + '</span>' : '—') +
            (c.current == null ? '' : cell('החודש', '<span class="num">' + money(c.current) + '</span>'));
    }
    show(catTrend.categories[0].key);

    document.addEventListener('click', function (e) {
        const chip = e.target.closest && e.target.closest('.cat-trend-chips .tx-cat-chip');
        if (!chip) return;
        document.querySelectorAll('.cat-trend-chips .tx-cat-chip').forEach(function (b) {
            b.classList.toggle('active', b === chip);
            b.setAttribute('aria-pressed', b === chip ? 'true' : 'false');
        });
        show(chip.dataset.key);
    });
}

})();


/* ═══ האינטראקטיביות של העמוד ═══ */
(function () {

// לחיצה בכל מקום בשורה פותחת את החודש. הקישור עצמו (שם החודש) הוא מה
// שמקלדת וקורא מסך פוגשים; השורה רק מגדילה את אזור הלחיצה לאצבע.
document.addEventListener('click', function (e) {
    const row = e.target.closest('.months-table tr.month-row[data-href]');
    if (!row || e.target.closest('a')) return;
    window.location.href = row.dataset.href;
});
})();
