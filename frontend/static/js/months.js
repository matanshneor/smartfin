const SF_VIEW = window.sfData('sf-view-data');

/* ═══ הגרף ═══  (ראו chart-setup.js)
 * בלוק נפרד מ"הצג עוד" שלמטה: כשהספרייה לא נטענת, הכפתור עדיין עובד. */
(function () {
if (!window.sfCharts.ready) return;

const TEXT_MUTED = window.sfCharts.muted;
const GRID_LINE  = window.sfCharts.grid;

const trendData = SF_VIEW.trend;

// ── השוואת חודשים ──
if (trendData.length > 0) {
    const last6 = trendData.slice(-6);
    const ctx = document.getElementById('compareChart');
    if (ctx) {
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: last6.map(d => d.month_name),
                datasets: [
                    {
                        label:           'הכנסות',
                        data:            last6.map(d => d.income),
                        backgroundColor: 'rgba(61,107,84,0.9)',
                        borderRadius:    5,
                    },
                    {
                        label:           'הוצאות',
                        data:            last6.map(d => d.expense),
                        backgroundColor: 'rgba(160,69,69,0.9)',
                        borderRadius:    5,
                    },
                    {
                        label:           'חיסכון',
                        data:            last6.map(d => d.savings),
                        backgroundColor: 'rgba(166,124,0,0.9)',
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
                        labels: { boxWidth: 12, padding: 16, font: { size: 12 }, color: TEXT_MUTED }
                    },
                    tooltip: {
                        callbacks: {
                            label: c => ` ${c.dataset.label}: ₪${c.parsed.y.toLocaleString('en-US')}`
                        }
                    }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 11 } } },
                    y: {
                        grid: { color: GRID_LINE },
                        ticks: { font: { size: 11 }, callback: v => '₪' + v.toLocaleString('en-US') }
                    }
                }
            }
        });
    }
}

})();


/* ═══ האינטראקטיביות של העמוד ═══ */
(function () {

// "הצג עוד" — חושף את כל החודשים שמעבר ל-6 הראשונים (או מכווץ בחזרה)
const moreBtn = document.getElementById('showMoreMonths');
if (moreBtn) {
    const archive = document.getElementById('monthsArchive');
    moreBtn.addEventListener('click', function () {
        const open = archive.classList.toggle('show-all');
        moreBtn.textContent = open ? moreBtn.dataset.less : moreBtn.dataset.more;
        moreBtn.setAttribute('aria-expanded', open);
    });
}
})();
