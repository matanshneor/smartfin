(function () {
const newBtn    = document.getElementById('newProjectBtn');
const form      = document.getElementById('newProjectForm');
const cancelBtn = document.getElementById('cancelProjectBtn');
const errorEl   = document.getElementById('newProjectError');
const ownerSharedBtn   = document.getElementById('projectOwnerShared');
const ownerPersonalBtn = document.getElementById('projectOwnerPersonal');
let isPersonal = false;

[ownerSharedBtn, ownerPersonalBtn].forEach(function (btn) {
    btn.addEventListener('click', function () {
        ownerSharedBtn.classList.toggle('active', btn === ownerSharedBtn);
        ownerPersonalBtn.classList.toggle('active', btn === ownerPersonalBtn);
        isPersonal = btn.dataset.personal === 'true';
    });
});

newBtn.addEventListener('click', function () {
    form.style.display = form.style.display === 'none' ? '' : 'none';
});
cancelBtn.addEventListener('click', function () {
    form.style.display = 'none';
    form.reset();
    errorEl.textContent = '';
    isPersonal = false;
    ownerSharedBtn.classList.add('active');
    ownerPersonalBtn.classList.remove('active');
});

form.addEventListener('submit', function (e) {
    e.preventDefault();
    errorEl.textContent = '';
    const name = document.getElementById('projectName').value.trim();
    const icon = document.getElementById('projectIcon').value.trim();
    const description = document.getElementById('projectDescription').value.trim();
    const budgetVal = document.getElementById('projectBudget').value;
    const trackExpense = document.getElementById('projectTrackExpense').checked;
    const trackIncome  = document.getElementById('projectTrackIncome').checked;
    const trackSavings = document.getElementById('projectTrackSavings').checked;
    if (!name) { errorEl.textContent = 'נא להזין שם לפרויקט'; return; }
    if (!trackExpense && !trackIncome && !trackSavings) {
        errorEl.textContent = 'יש לבחור לפחות סוג עסקה אחד למעקב';
        return;
    }

    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    fetch('/api/projects', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            name: name,
            icon: icon,
            description: description,
            budget_target: budgetVal ? parseFloat(budgetVal) : null,
            is_personal: isPersonal,
            track_expense: trackExpense,
            track_income: trackIncome,
            track_savings: trackSavings,
        }),
    })
    .then(r => r.json())
    .then(function (data) {
        if (data.error) { submitBtn.disabled = false; errorEl.textContent = data.error; return; }
        window.location.reload();
    })
    .catch(function () { submitBtn.disabled = false; errorEl.textContent = 'שגיאת רשת — נסה שוב'; });
});

document.addEventListener('click', function (e) {
    const btn = e.target.closest('.delete-project-btn');
    if (!btn) return;
    const id  = btn.dataset.id;
    const row = btn.closest('.project-row');
    const name = row.querySelector('.project-name').textContent.trim();

    window.appConfirm({
        title: 'למחוק את "' + name + '"?',
        message: 'ההוצאות ששויכו לפרויקט לא יימחקו — הן פשוט יחזרו להיספר תחת הקטגוריה הרגילה שלהן.',
        confirmText: 'מחק פרויקט',
    }).then(function (ok) {
        if (!ok) return;
        // שאלה שנייה ונפרדת: מה לעשות עם העסקאות עצמן. ברירת מחדל
        // בטוחה (גם ב-Escape/לחיצה בחוץ) — להשאיר אותן כרגילות.
        return window.appConfirm({
            title: 'מה לעשות עם העסקאות של הפרויקט?',
            message: 'אפשר למחוק גם את כל ההוצאות/הכנסות/חיסכון ששויכו לפרויקט, או להשאיר אותן — הן פשוט יחזרו להיספר תחת הקטגוריה הרגילה שלהן.',
            confirmText: 'מחק גם עסקאות',
            cancelText: 'השאר כרגילות',
            danger: false,
        }).then(function (deleteTransactions) {
            fetch('/api/projects/' + id, {
                method:  'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ delete_transactions: deleteTransactions }),
            })
            .then(r => r.json())
            .then(function (d) {
                if (d.status === 'ok') {
                    row.style.transition = 'opacity 0.25s';
                    row.style.opacity = '0';
                    setTimeout(() => row.remove(), 260);
                    window.showToast('הפרויקט נמחק');
                } else {
                    window.showToast('המחיקה נכשלה', 'error');
                }
            })
            .catch(function () { window.showToast('שגיאת רשת — נסה שוב', 'error'); });
        });
    });
});
})();
