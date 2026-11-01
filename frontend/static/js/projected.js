/* מופע צפוי בחודש עתידי (מתן, 1.11): לחיצה שואלת מה לעשות —
 * "דלג על החודש הזה" (רק התאריך הזה לא יירשם; "בטל" בהודעה מחזיר אותו),
 * או "עריכת הסדרה" — העסקה הקבועה עצמה בהגדרות, וכל החודשים מתעדכנים. */
(function () {
    'use strict';

    const MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי',
                    'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר'];

    function send(row, skip) {
        return fetch('/api/recurring/' + encodeURIComponent(row.dataset.templateId) + '/skip', {
            method:  'PUT',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ date: row.dataset.date, skip: skip }),
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (d) {
                if (!r.ok || d.status !== 'ok') throw new Error(d.error || 'הפעולה נכשלה — נסו שוב');
            });
        });
    }

    function open(row) {
        const month = MONTHS[parseInt(row.dataset.date.slice(5, 7), 10) - 1];
        window.appConfirm({
            title:       row.dataset.label,
            message:     'עסקה קבועה שצפויה ב-' + parseInt(row.dataset.date.slice(8, 10), 10) + ' ב' + month + '.',
            confirmText: 'דילוג על ' + month,
            cancelText:  'עריכת העסקה הקבועה',
            danger:      false,
        }).then(function (skip) {
            if (skip === null) return;                       // נסגר בלי בחירה
            if (!skip) {
                location.href = '/settings?series=' + encodeURIComponent(row.dataset.templateId);
                return;
            }
            send(row, true).then(function () {
                // הסיכומים בראש העמוד מחושבים בשרת — טוענים מחדש אחרי ההודעה
                const reload = setTimeout(function () { location.reload(); }, 3500);
                // אותו מופע מופיע גם בפירוט הקטגוריה וגם ב"כל העסקאות"
                document.querySelectorAll('.cat-tx-row.is-projected').forEach(function (r) {
                    if (r.dataset.templateId === row.dataset.templateId && r.dataset.date === row.dataset.date) r.style.display = 'none';
                });
                window.showToast('דילגנו על ' + row.dataset.label + ' ב' + month, null, {
                    label: 'ביטול',
                    onClick: function () {
                        clearTimeout(reload);
                        send(row, false).then(function () { location.reload(); }, function (e) {
                            window.showToast(e.message, 'error');
                        });
                    },
                });
            }, function (e) { window.showToast(e.message, 'error'); });
        });
    }

    document.addEventListener('click', function (e) {
        const row = e.target.closest && e.target.closest('.cat-tx-row.is-projected[data-template-id]');
        if (row) open(row);
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const row = e.target.closest && e.target.closest('.cat-tx-row.is-projected[data-template-id]');
        if (row) { e.preventDefault(); open(row); }
    });
})();
