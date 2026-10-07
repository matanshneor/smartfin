const SF_VIEW = window.sfData('sf-view-data');


// מרכוז החודש הנוכחי ברצועה. ה"מגנט" עצמו כולו CSS — כאן רק ממקמים את
// נקודת ההתחלה. גם אחרי רענון רך (חזרה לאפליקציה, הוספת עסקה): הוא מחליף
// את ה-hero ברצועה חדשה שעומדת בהתחלה — מתן (1.10) ראה יולי-אוגוסט
// כשהחודש הנוכחי היה אוקטובר.
(function () {
function centerStrip() {
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
}
centerStrip();
window.addEventListener('sf:refreshed', centerStrip);
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
    const rows = document.querySelectorAll('#txScreen .tx-screen-list .cat-tx-row');
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
        // גם שם הקטגוריה והפרויקט (מתן, 5.10): "סופר" מוצא את "רמי לוי"
        const desc = ((row.querySelector('.cat-tx-desc') || {}).textContent || '')
                   + ' ' + (row.dataset.search || '');
        const match = (!q || desc.toLowerCase().indexOf(q) !== -1)
                   && (!type || row.dataset.type === type)
                   && (!cats.size || cats.has(row.dataset.catKey));
        row.style.display = match ? '' : 'none';
        if (match) { shown++; sum += parseFloat(row.dataset.amount) || 0; }
    });
    const filtering = q || type || cats.size;
    txState = { q: input ? input.value : '', type: type, cats: Array.from(cats) };
    if (emptyMsg) emptyMsg.style.display = (filtering && shown === 0) ? 'block' : 'none';
    // כשנבחרו קטגוריות — גם כמה יצא עליהן ("5 · ₪1,070")
    if (count) count.textContent = !filtering ? count.dataset.total
        : (cats.size ? shown + ' · ₪' + window.sfMoney(Math.round(sum)) : shown);
}

// ── המסך של כל העסקאות (מתן, 5.10) ──
// בתצוגה המקדימה 5 האחרונות; הרשימה המלאה, עם החיפוש והסינון, במסך משלה.
// ‎#all-tx‎ בכתובת: כפתור החזרה של הטלפון סוגר את המסך ולא יוצא מהחודש.
// עריכה מתוך המסך מרעננת את ‎main‎ (רענון רך) — והמסך החדש מגיע סגור, עם
// חיפוש ריק. אז הוא נפתח מחדש עם מה שהיה בו (‎txState‎).
let txState = null;

function txScreen() { return document.getElementById('txScreen'); }

// המסך עובר אל ‎body‎ ברגע הפתיחה. בתוך הכרטיס ‎position: fixed‎ לא מכסה את
// המסך — לכרטיסים יש אנימציית כניסה עם ‎transform‎, וזה הופך אותם לנקודת
// הייחוס. המסך נכלא בתוך הכרטיס, והכותרת הדביקה של החודש ישבה מעליו.
function openTxScreen(push) {
    const screen = txScreen();
    if (!screen) return;
    if (screen.parentElement !== document.body) document.body.appendChild(screen);
    screen.hidden = false;
    document.body.classList.add('tx-screen-open');
    if (push) {
        try { history.pushState({ sfTxScreen: true }, '', '#all-tx'); } catch (e) { /* לא קריטי */ }
    }
}

function hideTxScreen() {
    const screen = txScreen();
    if (screen) screen.hidden = true;
    document.body.classList.remove('tx-screen-open');
    txState = null;
}

function closeTxScreen() {
    if (history.state && history.state.sfTxScreen) { history.back(); return; }   // popstate מסתיר
    hideTxScreen();
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { /* לא קריטי */ }
}

function restoreTxState() {
    if (!txState) return;
    const input = document.getElementById('txSearch');
    if (input) input.value = txState.q;
    const typeChip = document.querySelector('.tx-type-chip[data-type="' + txState.type + '"]');
    if (typeChip) {
        document.querySelectorAll('.tx-type-chip').forEach(function (c) { pressChip(c, c === typeChip); });
        document.querySelectorAll('.tx-cat-chips').forEach(function (rowEl) {
            rowEl.hidden = rowEl.dataset.forType !== txState.type;
        });
    }
    const group = document.querySelector('.tx-cat-chips:not([hidden])');
    if (group && txState.cats.length) {
        group.querySelectorAll('.tx-cat-chip').forEach(function (c) {
            pressChip(c, c.dataset.cat ? txState.cats.indexOf(c.dataset.cat) !== -1 : false);
        });
    }
    filterAllTx();
}

document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    if (e.target.closest('#txScreenOpen')) openTxScreen(true);
    else if (e.target.closest('#txScreenClose')) closeTxScreen();
});
document.addEventListener('keydown', function (e) {
    const screen = txScreen();
    if (e.key === 'Escape' && !e.defaultPrevented && screen && !screen.hidden && !document.querySelector('.modal-overlay.open')) closeTxScreen();
});
window.addEventListener('popstate', function () {
    if (location.hash === '#all-tx') openTxScreen(false); else hideTxScreen();
});
window.addEventListener('sf:refreshed', function () {
    // הרענון הביא מסך חדש בתוך ‎main‎; העותק הישן שהועבר ל-‎body‎ מיותר
    document.querySelectorAll('body > #txScreen').forEach(function (old) {
        if (old !== document.querySelector('main #txScreen')) old.remove();
    });
    if (location.hash !== '#all-tx') return;
    const keep = txState;
    openTxScreen(false);
    txState = keep;
    restoreTxState();
});
try {
    if (location.hash === '#all-tx') openTxScreen(false);
} catch (err) { /* בלי פתיחה אוטומטית — לא בלי העמוד */ }

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



/* ═══ כותרת שנשארת למעלה בגלילה (מתן, 30.9 — סבב 6, פריט 12) ═══
 *
 * כשהמאזן החודשי יוצא מהמסך, בראש המסך מופיעה שורה דקה: שם החודש והמאזן.
 * נגיעה בה מחזירה לראש העמוד. נבנית מחדש אחרי רענון רך — אז הערכים חדשים.
 * הסכום נקרא מ-‎data-countup‎ ולא מהטקסט: באמצע אנימציית הספירה הטקסט הוא
 * מספר ביניים. */
(function () {
    let bar = null, observer = null;

    function build() {
        if (observer) { observer.disconnect(); observer = null; }
        const net = document.querySelector('.month-net');
        const title = document.querySelector('.hero-title');
        if (!net || !title || !('IntersectionObserver' in window)) { if (bar) bar.hidden = true; return; }
        if (!bar) {
            bar = document.createElement('button');
            bar.type = 'button';
            bar.className = 'month-sticky';
            bar.hidden = true;
            bar.setAttribute('aria-label', 'חזרה לראש החודש');
            bar.addEventListener('click', function () {
                const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
                window.scrollTo({ top: 0, behavior: calm ? 'auto' : 'smooth' });
            });
            document.body.appendChild(bar);
        }
        const valueEl = net.querySelector('.month-net-value');
        let value = valueEl ? valueEl.textContent.trim() : '';
        if (valueEl && valueEl.dataset.countup) {
            value = (valueEl.dataset.prefix || '') + '₪' + window.sfMoney(valueEl.dataset.countup);
        }
        bar.innerHTML = '';
        const t = document.createElement('span');
        t.className = 'month-sticky-title';
        t.textContent = title.textContent.trim();
        const v = document.createElement('span');
        v.className = 'month-sticky-value' + (net.classList.contains('deficit') ? ' deficit'
                                            : net.classList.contains('surplus') ? ' surplus' : '');
        v.textContent = 'מאזן ' + value;
        bar.append(t, v);
        observer = new IntersectionObserver(function (entries) {
            // מופיעה רק כשהמאזן יצא **למעלה** — לא כשהוא עוד לא הגיע למסך
            const e = entries[0];
            bar.hidden = e.isIntersecting || e.boundingClientRect.top > 0;
        });
        observer.observe(net);
    }
    build();
    window.addEventListener('sf:refreshed', build);
})();


/* ═══ קביעת תקציבים — חלון אחד לכל הקטגוריות (מתן, 30.9) ═══
 *
 * במקום "קביעת תקציב לקטגוריה" אחרי כל שורה, ששלח להגדרות. כל קטגוריית
 * הוצאה עם כמה יצא עליה החודש ושדה לתקציב החודשי; ריק = בלי תקציב. שמירה
 * אחת שולחת רק מה שהשתנה. הנתונים נקראים ב**פתיחה** (‎sf-budgets‎ בתוך
 * ‎main‎) — אחרי רענון רך הם כבר החדשים. */
(function () {
    let sheet = null;

    function budgetMoney(v) { return '₪' + window.sfMoney(v); }

    function buildBudgets(rows) {
        if (sheet) sheet.remove();
        sheet = document.createElement('div');
        sheet.className = 'color-sheet budget-sheet';
        sheet.setAttribute('role', 'dialog');
        sheet.setAttribute('aria-modal', 'true');
        sheet.setAttribute('aria-labelledby', 'budgetSheetTitle');
        const card = document.createElement('div');
        card.className = 'color-sheet-card budget-sheet-card';
        card.innerHTML = '<p class="color-sheet-title" id="budgetSheetTitle">תקציב חודשי לכל קטגוריה</p>'
            + '<p class="color-sheet-hint">סכום לחודש. שדה ריק — בלי תקציב לקטגוריה.</p>';
        const list = document.createElement('div');
        list.className = 'budget-sheet-list';
        rows.forEach(function (r) {
            const row = document.createElement('label');
            row.className = 'budget-sheet-row';
            const info = document.createElement('span');
            info.className = 'budget-sheet-info';
            const name = document.createElement('span');
            name.className = 'budget-sheet-name';
            name.textContent = (r.icon || '📦') + ' ' + r.name;
            const spent = document.createElement('span');
            spent.className = 'budget-sheet-spent';
            spent.textContent = 'החודש: ' + budgetMoney(r.total || 0);
            info.append(name, spent);
            const wrap = document.createElement('span');
            wrap.className = 'amount-input-wrap budget-sheet-amount';
            wrap.innerHTML = '<span class="amount-currency">₪</span>';
            const input = document.createElement('input');
            input.className = 'form-input amount-input';
            input.type = 'number';
            input.inputMode = 'numeric';
            input.min = '0';
            input.step = '1';
            input.placeholder = 'אין';
            input.value = r.budget ? Math.round(r.budget) : '';
            input.dataset.cat = r.category_id;
            input.dataset.old = r.budget ? String(Math.round(r.budget)) : '';
            input.dataset.alert = r.budget_alert === false ? 'false' : 'true';
            input.setAttribute('aria-label', 'תקציב חודשי ל' + r.name);
            wrap.appendChild(input);
            row.append(info, wrap);
            list.appendChild(row);
        });
        card.appendChild(list);
        const err = document.createElement('p');
        err.className = 'form-error';
        err.setAttribute('role', 'alert');
        card.appendChild(err);
        const actions = document.createElement('div');
        actions.className = 'edit-actions budget-sheet-actions';
        actions.innerHTML = '<button type="button" class="btn-sm btn-primary" data-save>שמירה</button>'
                          + '<button type="button" class="btn-sm btn-ghost" data-cancel>ביטול</button>';
        card.appendChild(actions);
        sheet.appendChild(card);
        document.body.appendChild(sheet);

        sheet.addEventListener('click', function (e) {
            if (e.target === sheet || e.target.closest('[data-cancel]')) { closeBudgets(); return; }
            if (!e.target.closest('[data-save]')) return;
            const limits = {};
            let bad = false;
            sheet.querySelectorAll('input[data-cat]').forEach(function (inp) {
                const v = inp.value.trim();
                if (v === inp.dataset.old) return;
                if (v === '' || Number(v) === 0) { limits[inp.dataset.cat] = null; return; }
                const n = Number(v);
                if (!isFinite(n) || n < 0) { bad = true; inp.setAttribute('aria-invalid', 'true'); return; }
                limits[inp.dataset.cat] = { amount: Math.round(n), alert: inp.dataset.alert !== 'false' };
            });
            if (bad) { err.textContent = 'נא להזין סכומים חיוביים בלבד'; return; }
            if (!Object.keys(limits).length) { closeBudgets(); return; }
            const save = e.target.closest('[data-save]');
            save.disabled = true;
            save.textContent = 'שומר…';
            fetch('/api/family/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ limits: limits }),
            })
                .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; }); })
                .then(function (res) {
                    if (!res.ok) {
                        err.textContent = res.d.error || 'שמירת התקציבים נכשלה';
                        save.disabled = false; save.textContent = 'שמירה';
                        return;
                    }
                    closeBudgets();
                    if (window.sfForgetCategories) window.sfForgetCategories();
                    window.softReload(null, 'התקציבים נשמרו').then(function (how) {
                        if (how !== 'reloaded') window.showToast('התקציבים נשמרו');
                    });
                })
                .catch(function () {
                    err.textContent = window.sfNetError();
                    save.disabled = false; save.textContent = 'שמירה';
                });
        });
    }

    function closeBudgets() {
        // קודם ‎hidden‎ — החלון יורד באותו מסלול שעלה (style.css, ‎.color-sheet‎) —
        // ורק אחרי התנועה יוצא מהעמוד. ‎sheet‎ מתאפס מיד: פתיחה חדשה בונה חלון חדש.
        if (sheet) {
            const gone = sheet;
            sheet = null;
            gone.hidden = true;
            setTimeout(function () { gone.remove(); }, 300);
        }
        const btn = document.getElementById('budgetsOpen');
        if (btn) btn.focus({ preventScroll: true });
    }

    document.addEventListener('click', function (e) {
        if (!e.target.closest || !e.target.closest('#budgetsOpen')) return;
        let rows = [];
        try { rows = JSON.parse((document.getElementById('sf-budgets') || {}).textContent || '[]'); }
        catch (err) { rows = []; }
        if (!rows.length) return;
        buildBudgets(rows);
        const first = sheet.querySelector('input');
        if (first) first.focus({ preventScroll: true });
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sheet) closeBudgets();
    });
})();


/* ═══ החלקה בין חודשים (מתן, 3.10 — רעיון 35) ═══
 *
 * על המאזן והריבועים בלבד — לא על רצועת החודשים (יש לה גלילה משלה) ולא על
 * שאר העמוד (שורות עסקה מחליקים לעריכה ומחיקה, וגרפים). כמו בכרטיס "השבוע":
 * הזמן זורם מימין לשמאל, אז גרירה שמאלה = החודש הקודם, ימינה = הבא.
 * נעילת כיוון אחרי 8px: הצידה — המסך לא זז והאזור זז עם האצבע; גלילה — כרגיל.
 * בהגדרת הכיוון מתחילה כבר טעינת החודש (ראו ‎sw.js‎, רעיון 29). */
(function () {
    const ZONE = '.month-net, .kpi-chips';
    let sx = null, sy = 0, axis = null, target = null;

    function parts() { return document.querySelectorAll(ZONE); }
    function link(older) {
        return document.querySelector('.stats-nav-btn[aria-label="' + (older ? 'חודש קודם' : 'חודש הבא') + '"]');
    }
    function move(px, animate) {
        parts().forEach(function (el) {
            el.style.transition = animate ? 'transform 0.2s ease-out' : '';
            el.style.transform = px ? 'translateX(' + px + 'px)' : '';
        });
    }

    document.addEventListener('touchstart', function (e) {
        const zone = e.target.closest && e.target.closest(ZONE);
        if (!zone || e.touches.length !== 1) { sx = null; return; }
        sx = e.touches[0].clientX; sy = e.touches[0].clientY; axis = null; target = null;
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
        if (sx === null) return;
        const dx = e.touches[0].clientX - sx, dy = e.touches[0].clientY - sy;
        if (!axis) {
            if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
            axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
            if (axis === 'x') {
                target = link(dx < 0);
                const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
                if (target && sw) {
                    const u = new URL(target.href, location.href);
                    sw.postMessage({ type: 'prefetch', url: u.pathname + u.search });
                }
            }
        }
        if (axis !== 'x') return;
        e.preventDefault();
        move(Math.round(dx * 0.45));
    }, { passive: false });

    document.addEventListener('touchend', function (e) {
        if (sx === null) return;
        const dx = e.changedTouches[0].clientX - sx;
        const wasX = axis === 'x';
        sx = null; axis = null;
        if (!wasX) return;
        const go = Math.abs(dx) >= 50 && link(dx < 0);
        if (!go) { move(0, true); return; }
        move(dx < 0 ? -60 : 60, true);
        window.location.href = go.href;
    }, { passive: true });

    document.addEventListener('touchcancel', function () {
        if (sx !== null) move(0, true);
        sx = null; axis = null;
    }, { passive: true });

    // חזרה עם "אחורה" — הדפדפן משחזר את העמוד כמו שהיה, כולל ההזזה
    window.addEventListener('pageshow', function () { move(0); });
})();
