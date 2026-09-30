const SF_VIEW = window.sfData('sf-view-data');


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
    // קורא מסך לא רואה את החץ שמתהפך — צריך לשמוע "מורחב"/"מכווץ"
    toggle.setAttribute('aria-expanded', String(shown));
});


// ── מהריבועים (וכרטיסי הבית) אל הפירוט: גלילה והבהוב ──
// ‎:target‎ לא מתעדכן ב-‎replaceState‎, אז ההבהוב במחלקה. הגעה מהבית היא
// ניווט רגיל עם ‎#‎ — הדפדפן גולל בעצמו, ורק ההבהוב נוסף כאן.
const BREAKDOWNS = ['income-breakdown', 'expense-breakdown', 'savings-breakdown'];

function flashBreakdown(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    el.classList.remove('flash');
    void el.offsetWidth;                  // מאתחל את האנימציה גם בלחיצה חוזרת
    el.classList.add('flash');
    return el;
}

document.addEventListener('click', function (e) {
    const link = e.target.closest('a.kpi-link');
    if (!link) return;
    const id = (link.getAttribute('href') || '').slice(1);
    const el = flashBreakdown(id);
    if (!el) return;                      // אין פירוט — הקישור מתנהג כרגיל
    e.preventDefault();
    const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' });
    try { history.replaceState(null, '', '#' + id); } catch (err) { /* לא קריטי */ }
});

// הגנה על ‎location‎: שורה ברמת הקובץ שזורקת מפילה את כל month.js — גרפים,
// מקרא, פתיחת קטגוריות (כך בדיוק נפל core.js פעם על sessionStorage)
try {
    const arrived = window.location.hash.slice(1);
    if (BREAKDOWNS.includes(arrived)) flashBreakdown(arrived);
} catch (err) { /* בלי הבהוב — לא בלי העמוד */ }

// ── חיפוש/סינון ברשימת "כל העסקאות" (client-side) ──
//
// בהאצלה מ-document ולא בהאזנה ישירה, ובלי לשמור את השורות מראש:
// רענון רך מחליף את ‎main‎ כולו, וכל הפניה שנתפסה בטעינה מצביעה אחר כך
// על אלמנטים מנותקים. החיפוש פשוט הפסיק להגיב, בלי שום סימן.
// החיפוש והסינון לפי סוג (מתן, 30.9) פועלים יחד: שורה מוצגת רק אם היא
// מתאימה לשניהם. הסוג הפעיל נקרא מהכפתור עצמו ולא נשמר במשתנה — מאותה
// סיבה: אחרי רענון רך הכפתורים חדשים, וחוזרים ל"הכל".
function filterAllTx() {
    const rows = document.querySelectorAll(
        '.all-tx-header + .tx-search-wrap + .cat-tx-list .cat-tx-row');
    const input = document.getElementById('txSearch');
    const emptyMsg = document.getElementById('txSearchEmpty');
    const count = document.querySelector('.all-tx-count');
    const activeChip = document.querySelector('.tx-type-chip.active');
    const type = activeChip ? activeChip.dataset.type : '';
    // הקטגוריות שנבחרו בשורה הפתוחה (ריק = "כל ההוצאות")
    const cats = new Set();
    document.querySelectorAll('.tx-cat-chips:not([hidden]) .tx-cat-chip.active').forEach(function (c) {
        if (c.dataset.cat) cats.add(c.dataset.cat);
    });
    const q = input ? input.value.trim().toLowerCase() : '';
    let shown = 0, sum = 0;
    rows.forEach(function (row) {
        const desc = (row.querySelector('.cat-tx-desc') || {}).textContent || '';
        const match = (!q || desc.toLowerCase().indexOf(q) !== -1)
                   && (!type || row.dataset.type === type)
                   && (!cats.size || cats.has(row.dataset.catKey));
        row.style.display = match ? '' : 'none';
        if (match) { shown++; sum += parseFloat(row.dataset.amount) || 0; }
    });
    const filtering = q || type || cats.size;
    if (emptyMsg) emptyMsg.style.display = (filtering && shown === 0) ? 'block' : 'none';
    // כשנבחרו קטגוריות — גם כמה יצא עליהן ("5 · ₪1,070")
    if (count) count.textContent = !filtering ? count.dataset.total
        : (cats.size ? shown + ' · ₪' + window.sfMoney(Math.round(sum)) : shown);
}

function pressChip(chip, on) {
    chip.classList.toggle('active', on);
    chip.setAttribute('aria-pressed', on ? 'true' : 'false');
}

document.addEventListener('input', function (e) {
    if (e.target && e.target.id === 'txSearch') filterAllTx();
});

document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    const typeChip = e.target.closest('.tx-type-chip');
    const catChip = e.target.closest('.tx-cat-chip');
    if (typeChip) {
        // סוג חדש: פותחים את שורת הקטגוריות שלו, וכל שורה חוזרת ל"כל ה…"
        document.querySelectorAll('.tx-type-chip').forEach(function (c) { pressChip(c, c === typeChip); });
        document.querySelectorAll('.tx-cat-chips').forEach(function (rowEl) {
            rowEl.hidden = rowEl.dataset.forType !== typeChip.dataset.type;
            rowEl.querySelectorAll('.tx-cat-chip').forEach(function (c) { pressChip(c, !c.dataset.cat); });
        });
    } else if (catChip) {
        const group = catChip.closest('.tx-cat-chips');
        const allChip = group.querySelector('.tx-cat-chip[data-cat=""]');
        if (!catChip.dataset.cat) {
            // "כל ההוצאות" — מבטל את כל הבחירות
            group.querySelectorAll('.tx-cat-chip').forEach(function (c) { pressChip(c, c === allChip); });
        } else {
            // קטגוריה: נגיעה מוסיפה, נגיעה נוספת מורידה
            pressChip(catChip, !catChip.classList.contains('active'));
            const any = group.querySelector('.tx-cat-chip.active:not([data-cat=""])');
            pressChip(allChip, !any);
        }
    } else {
        return;
    }
    filterAllTx();
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
const SF_VIEW = view;

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
                            label: c => ` ₪${window.sfMoney(c.parsed)} (${expenseData[c.dataIndex].pct}%)`
                        }
                    }
                }
            }
        }));
    }
}

// ── 4. הכנסות — אותו גרף עגול כמו ההוצאות (מתן, 30.9). לחיסכון אין גרף ──
// הצבעים מהשרת: בן המשפחה, או אפור ל"הכנסות נוספות".
[['incomeChart', SF_VIEW.income || [], 'color']]
.forEach(function (spec) {
    const ctx = document.getElementById(spec[0]);
    const data = spec[1];
    if (!ctx || !data.length) return;
    drawn.push(new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.map(d => d.name),
            datasets: [{
                data:            data.map(d => d.total),
                backgroundColor: spec[2] ? data.map(d => d[spec[2]]) : COLORS.slice(0, data.length),
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
                        label: c => ` ₪${window.sfMoney(c.parsed)} (${data[c.dataIndex].pct}%)`
                    }
                }
            }
        }
    }));
});

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
                        label: c => ` ${mb.label}: ₪${window.sfMoney(c.parsed.y)}`
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
