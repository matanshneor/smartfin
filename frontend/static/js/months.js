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
                    },
                    {
                        label:           'הוצאות',
                        data:            last6.map(d => d.expense),
                        backgroundColor: 'rgba(160,69,69,0.9)',
                        borderRadius:    5,
                    },
                    {
                        label:           'הכנסות',
                        data:            last6.map(d => d.income),
                        backgroundColor: 'rgba(61,107,84,0.9)',
                        borderRadius:    5,
                    }
                ]
            },
            options: {
                responsive:          true,
                maintainAspectRatio: false,
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
