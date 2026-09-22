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
    // ‎.zero-toggle‎ מסומן ‎role="button" tabindex="0"‎, אבל טופל ב-‎click‎
    // בלבד — ואלמנט שאינו ‎<button>‎ לא מייצר click מ-Enter. שלוש תחנות
    // Tab בכל עמוד חודש הכריזו על עצמן ככפתור ולא עשו כלום, ומשתמשי
    // מקלדת פשוט לא יכלו להגיע לקטגוריות המוסתרות.
    const zero = e.target.closest('.zero-toggle');
    if (zero) { e.preventDefault(); zero.click(); }
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
//
// נבנה מחדש אחרי רענון רך: ה-HTML הטרי מביא ‎<ul>‎ ריק, אז בלי זה
// הכרטיס נשאר עם דונאט ובלי המספרים שהוא מצייר.
function buildOverviewLegend() {
    const legend = document.getElementById('overviewLegend');
    if (!legend) return;
    const view = window.sfData('sf-view-data');
    const parts = [
        { label: 'הוצאות', value: (view.summary || {}).expense || 0, color: '#A04545' },
        { label: 'חיסכון', value: (view.summary || {}).savings || 0, color: '#A67C00' },
    ].filter(p => p.value > 0);
    const total = parts.reduce((sum, p) => sum + p.value, 0);

    legend.innerHTML = '';
    if (total <= 0) return;
    parts.forEach(p => {
        const li = document.createElement('li');
        li.className = 'legend-item';
        li.innerHTML = `
            <span class="legend-dot" style="background:${p.color}"></span>
            <span class="legend-name">${p.label}</span>
            <span class="legend-pct">${Math.round(p.value / total * 100)}%</span>
            <span class="legend-amount">₪${p.value.toLocaleString('en-US')}</span>`;
        legend.appendChild(li);
    });
}
buildOverviewLegend();
window.addEventListener('sf:refreshed', buildOverviewLegend);

// ── חיפוש/סינון ברשימת "כל העסקאות" (client-side) ──
//
// בהאצלה מ-document ולא בהאזנה ישירה, ובלי לשמור את השורות מראש:
// רענון רך מחליף את ‎main‎ כולו, וכל הפניה שנתפסה בטעינה מצביעה אחר כך
// על אלמנטים מנותקים. החיפוש פשוט הפסיק להגיב, בלי שום סימן.
document.addEventListener('input', function (e) {
    if (!e.target || e.target.id !== 'txSearch') return;
    const rows = document.querySelectorAll(
        '.all-tx-header + .tx-search-wrap + .cat-tx-list .cat-tx-row');
    const emptyMsg = document.getElementById('txSearchEmpty');
    const q = e.target.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach(function (row) {
        const desc = (row.querySelector('.cat-tx-desc') || {}).textContent || '';
        const match = !q || desc.toLowerCase().indexOf(q) !== -1;
        row.style.display = match ? '' : 'none';
        if (match) shown++;
    });
    if (emptyMsg) emptyMsg.style.display = (q && shown === 0) ? 'block' : 'none';
});

})();


/* ═══ הגרפים ═══  (ראו chart-setup.js)
 *
 * נצבעים מחדש אחרי רענון רך. ‎softReload‎ מחליף את ‎main‎ כולו, כלומר
 * כל ה-canvas מוחלפים — ומופעי Chart.js הישנים נשארו מחוברים לאלמנטים
 * מנותקים בזמן שהחדשים לא צוירו מעולם. התוצאה על המסך הייתה תוויות
 * מרכז מרחפות מעל ריבועים ריקים, שנראית כמו קריסה של העמוד.
 */
(function () {
if (!window.sfCharts.ready) return;

const COLORS    = window.sfCharts.colors;
const GRID_LINE = window.sfCharts.grid;

let drawn = [];

function paint() {
// מופעים קודמים נהרסים לפני הציור: ‎new Chart‎ על canvas תפוס זורק.
drawn.forEach(function (c) { try { c.destroy(); } catch (e) {} });
drawn = [];

// נתוני התצוגה מגיעים מאי-נתונים ב-HTML, ואותו HTML הוחלף — אז
// קוראים אותו מחדש ולא מסתמכים על מה שנקרא בטעינה.
const view = window.sfData('sf-view-data');
const parts = [
    { label: 'הוצאות', value: (view.summary || {}).expense || 0, color: '#A04545' },
    { label: 'חיסכון', value: (view.summary || {}).savings || 0, color: '#A67C00' },
].filter(p => p.value > 0);
const OVERVIEW_TOTAL = parts.reduce((s, p) => s + p.value, 0);
const SF_VIEW = view;
if (parts.length) {
    const outTotal = OVERVIEW_TOTAL;
    const ctx = document.getElementById('overviewChart');
    if (ctx) {
        drawn.push(new Chart(ctx, {
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
        }));
    }
}

// ── 2. הוצאות לפי קטגוריה ──
const expenseData = SF_VIEW.expense;
if (expenseData.length > 0) {
    const ctx = document.getElementById('expenseChart');
    if (ctx) {
        drawn.push(new Chart(ctx, {
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
        }));
    }
}

// ── 5. חלוקה בין בני המשפחה — גרף נפרד לכל סוג שהמשפחה הפעילה בו שיוך ──
SF_VIEW.members.forEach(function (mb) {
    const ctx = document.getElementById('membersChart-' + mb.type);
    if (!ctx || !mb.rows.length) return;
    drawn.push(new Chart(ctx, {
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
    }));
});

}   // paint

paint();

// רענון רך החליף את ‎main‎ — ה-canvas שעליהם ציירנו כבר לא במסמך.
window.addEventListener('sf:refreshed', paint);

})();

/* ─── ניהול העסקאות הקבועות, במקום ─────────────────────────────────────────
 *
 * הכפתור הזה היה קישור להגדרות. מי שעמד כאן וראה ששכר הדירה שגוי נשלח
 * לעמוד אחר, לגלול, ולמצוא שם את אותה שורה בדיוק — במקום לגעת בזו שמולו.
 *
 * העריכה עצמה אינה נכתבת כאן: הוספת ‎recurring-row‎ לשורה מספיקה כדי
 * שהמודאל הגלובלי ב-transactions.js יטפל בה, בדיוק כמו בהגדרות. השורות
 * לא נושאות את הסיווג כברירת מחדל כי מחוץ למצב ניהול הרשימה היא תצוגה:
 * לחיצה מקרית על "קבוע כל חודש" לא אמורה לפתוח עורך.
 */
(function () {
    // האצלה מ-document ולא האזנה ישירה: רענון רך מחליף את ‎main‎, ועם
    // האזנה ישירה הכפתור שרד על המסך ומת בלחיצה.
    function setManaging(list, btn, on) {
        list.classList.toggle('managing', on);
        btn.setAttribute('aria-expanded', String(on));
        btn.textContent = on ? 'סיום' : 'ניהול';
        list.querySelectorAll('.fixed-row').forEach(function (row) {
            row.classList.toggle('recurring-row', on);
            // מחוץ למצב ניהול השורה אינה יעד מקלדת ואינה מוכרזת ככפתור
            if (on) {
                row.setAttribute('role', 'button');
                row.setAttribute('tabindex', '0');
            } else {
                row.removeAttribute('role');
                row.removeAttribute('tabindex');
            }
            const x = row.querySelector('.delete-recurring-btn');
            if (x) x.tabIndex = on ? 0 : -1;
        });
    }

    document.addEventListener('click', function (e) {
        const btn = e.target.closest && e.target.closest('#fixedManageBtn');
        if (!btn) return;
        const list = document.getElementById('fixedList');
        if (!list) return;
        setManaging(list, btn, !list.classList.contains('managing'));
    });
})();
