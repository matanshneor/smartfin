/* צפייה בקבלה בתוך האפליקציה (מתן, 12.10).
 *
 * אייקון הקבלה הוא ‎<a href="/receipts/<id>" target="_blank">‎ — ובאפליקציה
 * המותקנת הוא הוציא לספארי. עכשיו נגיעה פותחת את התמונה כאן, על מסך כהה:
 * נגיעה בתמונה מגדילה (ושוב — מקטינה), ✕, Escape או החלקה למטה סוגרים.
 * הקישור עצמו נשאר: לחיצה עם Cmd/Ctrl, לחיצה ארוכה ו"פתיחה בלשונית חדשה"
 * עובדים כמו קודם, ואם התמונה לא נטענה — יש קישור לפתיחה רגילה.
 * (בלי ‎window.open‎ מ-JS — iOS חוסם אותו; ראו ‎test_receipt_viewing‎.) */
(function () {
    'use strict';
    let box = null, img = null, fail = null, failLink = null, lastFocus = null, startY = null;

    function build() {
        box = document.createElement('div');
        box.className = 'receipt-viewer';
        box.setAttribute('role', 'dialog');
        box.setAttribute('aria-modal', 'true');
        box.setAttribute('aria-label', 'קבלה');
        box.hidden = true;
        box.innerHTML =
            '<button type="button" class="receipt-viewer-close" aria-label="סגירה">✕</button>' +
            '<div class="receipt-viewer-stage"><img alt="הקבלה המצורפת"></div>' +
            '<p class="receipt-viewer-fail" hidden>לא הצלחנו להציג את הקבלה כאן. ' +
            '<a target="_blank" rel="noopener">פתיחה בלשונית</a></p>';
        document.body.appendChild(box);
        img = box.querySelector('img');
        fail = box.querySelector('.receipt-viewer-fail');
        failLink = fail.querySelector('a');
        box.querySelector('.receipt-viewer-close').addEventListener('click', close);
        img.addEventListener('click', function () { box.classList.toggle('zoomed'); });
        img.addEventListener('error', function () { img.hidden = true; fail.hidden = false; });
        box.addEventListener('click', function (e) { if (e.target === box) close(); });
        box.addEventListener('touchstart', function (e) {
            startY = (!box.classList.contains('zoomed') && e.touches.length === 1) ? e.touches[0].clientY : null;
        }, { passive: true });
        box.addEventListener('touchend', function (e) {
            if (startY != null && e.changedTouches[0].clientY - startY > 90) close();
            startY = null;
        });
    }

    function open(href) {
        if (!box) build();
        lastFocus = document.activeElement;
        box.classList.remove('zoomed');
        img.hidden = false;
        fail.hidden = true;
        failLink.href = href;
        img.src = href;
        box.hidden = false;
        document.body.style.overflow = 'hidden';
        box.querySelector('.receipt-viewer-close').focus();
    }

    function close() {
        if (!box || box.hidden) return;
        box.hidden = true;
        img.removeAttribute('src');
        document.body.style.overflow = '';
        if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    document.addEventListener('click', function (e) {
        const a = e.target.closest && e.target.closest('a.receipt-badge');
        if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        open(a.href);
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
})();
