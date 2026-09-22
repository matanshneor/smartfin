const SF_VIEW = window.sfData('sf-view-data');

(function () {
const projectId = document.getElementById('projectCategoriesArea').dataset.projectId;
const detailUrl = SF_VIEW.detailUrl;

// ── עריכת פרטי הפרויקט ──
const editForm  = document.getElementById('editProjectForm');
const editError = document.getElementById('editProjectError');

editForm.addEventListener('submit', function (e) {
    e.preventDefault();
    editError.textContent = '';
    const name = document.getElementById('editProjectName').value.trim();
    const icon = document.getElementById('editProjectIcon').value.trim();
    const description = document.getElementById('editProjectDescription').value.trim();
    const budgetVal = document.getElementById('editProjectBudget').value;
    const trackExpense = document.getElementById('editProjectTrackExpense').checked;
    const trackIncome  = document.getElementById('editProjectTrackIncome').checked;
    const trackSavings = document.getElementById('editProjectTrackSavings').checked;
    if (!name) { editError.textContent = 'נא להזין שם לפרויקט'; return; }
    if (!trackExpense && !trackIncome && !trackSavings) {
        editError.textContent = 'יש לבחור לפחות סוג עסקה אחד למעקב';
        return;
    }

    const editSubmitBtn = editForm.querySelector('button[type="submit"]');
    editSubmitBtn.disabled = true;
    fetch('/api/projects/' + projectId, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            name: name,
            icon: icon,
            description: description,
            budget_target: budgetVal ? parseFloat(budgetVal) : null,
            track_expense: trackExpense,
            track_income: trackIncome,
            track_savings: trackSavings,
        }),
    })
    .then(r => r.json())
    .then(function (data) {
        if (data.error) { editSubmitBtn.disabled = false; editError.textContent = data.error; return; }
        sessionStorage.setItem('sf_toast', 'הפרויקט עודכן');
        window.location.href = detailUrl;
    })
    .catch(function () { editSubmitBtn.disabled = false; editError.textContent = window.sfNetError(); });
});

// ── הפיכת פרויקט אישי למשותף / החזרתו להיות אישי ──
const shareBtn   = document.getElementById('shareProjectBtn');
const unshareBtn = document.getElementById('unshareProjectBtn');

if (shareBtn) {
    shareBtn.addEventListener('click', function () {
        window.appConfirm({
            title: 'להפוך את הפרויקט למשותף?',
            message: 'כל בני המשפחה יראו את הפרויקט, וההוצאות/הכנסות שכבר נרשמו בו יהפכו לשיוך משותף. תמיד תוכל להחזיר אותו להיות אישי בעצמך בעתיד.',
            confirmText: 'הפוך למשותף',
            danger: false,
        }).then(function (ok) {
            if (!ok) return;
            fetch('/api/projects/' + projectId + '/share', { method: 'PUT' })
            .then(r => r.json())
            .then(function (d) {
                if (d.error) { window.showToast(d.error, 'error'); return; }
                window.location.reload();
            })
            .catch(function () { window.showToast(window.sfNetError(), 'error'); });
        });
    });
}

if (unshareBtn) {
    unshareBtn.addEventListener('click', function () {
        window.appConfirm({
            title: 'להחזיר את הפרויקט להיות אישי?',
            message: 'רק אתה תראה את הפרויקט מעכשיו. עסקאות שכבר נרשמו כמשותפות יישארו כך.',
            confirmText: 'החזר להיות אישי',
            danger: false,
        }).then(function (ok) {
            if (!ok) return;
            fetch('/api/projects/' + projectId + '/unshare', { method: 'PUT' })
            .then(r => r.json())
            .then(function (d) {
                if (d.error) { window.showToast(d.error, 'error'); return; }
                window.location.reload();
            })
            .catch(function () { window.showToast(window.sfNetError(), 'error'); });
        });
    });
}

// ── קטגוריות הפרויקט (מנוהלות תמיד במסך העריכה) ──
const catTabs  = document.querySelectorAll('.project-cat-tabs .toggle-btn');
const catList  = document.getElementById('projectCatList');
const addForm  = document.getElementById('addProjectCatForm');
const addError = document.getElementById('addProjectCatError');
let currentTab = catTabs.length ? catTabs[0].dataset.catTab : null;

function catRowInnerHTML(id, icon, name) {
    return `
        <span class="cat-row-icon">${escapeHtml(icon)}</span>
        <span class="cat-row-name">${escapeHtml(name)}</span>
        <button class="edit-cat-btn" data-id="${escapeHtml(id)}" aria-label="ערוך קטגוריה">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
            </svg>
        </button>
        <button class="delete-cat-btn" data-id="${escapeHtml(id)}" aria-label="מחק קטגוריה">✕</button>
    `;
}

function renderCatRow(cat) {
    const li = document.createElement('li');
    li.className = 'category-row';
    li.dataset.id = cat.id;
    li.dataset.name = cat.name;
    li.dataset.icon = cat.icon;
    li.innerHTML = catRowInnerHTML(cat.id, cat.icon, cat.name);
    return li;
}

function loadCats(type) {
    catList.innerHTML = '<li class="category-row"><span class="cat-row-name">טוען…</span></li>';
    fetch('/api/projects/' + projectId + '/categories?type=' + type)
        .then(r => r.json())
        .then(function (cats) {
            if (currentTab !== type) return;
            catList.innerHTML = '';
            cats.forEach(cat => catList.appendChild(renderCatRow(cat)));
        })
        .catch(function () {
            catList.innerHTML = '';
            window.showToast(window.sfNetError(), 'error');
        });
}

catTabs.forEach(function (btn) {
    btn.addEventListener('click', function () {
        catTabs.forEach(function (b) {
            b.classList.remove('active');
            b.setAttribute('aria-selected', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        currentTab = btn.dataset.catTab;
        loadCats(currentTab);
    });
});

if (currentTab) loadCats(currentTab);

if (addForm) {
    addForm.addEventListener('submit', function (e) {
        e.preventDefault();
        addError.textContent = '';
        const icon = document.getElementById('newProjectCatIcon').value.trim() || '🏷';
        const name = document.getElementById('newProjectCatName').value.trim();
        if (!name) { addError.textContent = 'נא להזין שם קטגוריה'; return; }

        const addCatBtn = addForm.querySelector('button[type="submit"]');
        addCatBtn.disabled = true;
        fetch('/api/projects/' + projectId + '/categories', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ name, icon, type: currentTab }),
        })
        .then(r => r.json())
        .then(function (cat) {
            addCatBtn.disabled = false;
            if (cat.error) { addError.textContent = cat.error; return; }
            catList.appendChild(renderCatRow(cat));
            document.getElementById('newProjectCatName').value = '';
            document.getElementById('newProjectCatIcon').value = '🏷';
        })
        .catch(function () { addCatBtn.disabled = false; addError.textContent = window.sfNetError(); });
    });
}

document.addEventListener('click', function (e) {
    const btn = e.target.closest('.delete-cat-btn');
    if (!btn) return;
    const id  = btn.dataset.id;
    const row = btn.closest('.category-row');
    const name = (row.querySelector('.cat-row-name') || {}).textContent || '';

    window.appConfirm({
        title: 'למחוק את "' + name.trim() + '"?',
        message: 'עסקאות קיימות בקטגוריה יישארו, אך יוצגו ללא קטגוריה.',
        confirmText: 'מחק קטגוריה',
    }).then(function (ok) {
        if (!ok) return;
        fetch('/api/projects/' + projectId + '/categories/' + id, { method: 'DELETE' })
        .then(r => r.json())
        .then(function (d) {
            if (d.status === 'ok') {
                row.style.transition = 'opacity 0.25s';
                row.style.opacity = '0';
                setTimeout(() => row.remove(), 260);
                window.showToast('הקטגוריה נמחקה');
            } else {
                window.showToast('המחיקה נכשלה', 'error');
            }
        })
        // בלי ‎.catch‎ — כל שאר המחיקות בקובץ יש להן — חיבור שנופל
        // השאיר את השורה על המסך בלי שום הודעה, רק דחייה לא מטופלת
        // בקונסולה. המשתמש לוחץ ✕ שוב ושוב.
        .catch(function () { window.showToast(window.sfNetError(), 'error'); });
    });
});

// ── עריכת קטגוריה (inline) — מחקה את זרימת העריכה של קטגוריות המשפחה ──
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.edit-cat-btn');
    if (!btn) return;
    const row = btn.closest('.category-row');
    if (!row || row.classList.contains('editing')) return;

    const id       = btn.dataset.id;
    const origIcon = row.dataset.icon || '📦';
    const origName = row.dataset.name || '';

    row.classList.add('editing');
    row.dataset.origHtml = row.innerHTML;
    row.innerHTML = `
        <div class="cat-edit-form">
            <div class="add-cat-row">
                <input class="form-input emoji-input cat-edit-icon" type="text" maxlength="2" aria-label="אייקון">
                <input class="form-input cat-edit-name" type="text" maxlength="30" aria-label="שם קטגוריה">
            </div>
            <div class="edit-actions">
                <button class="btn-sm btn-primary cat-edit-save" data-id="${escapeHtml(id)}">שמור</button>
                <button class="btn-sm btn-ghost cat-edit-cancel">ביטול</button>
            </div>
        </div>
    `;
    row.querySelector('.cat-edit-icon').value = origIcon;
    row.querySelector('.cat-edit-name').value = origName;
    row.querySelector('.cat-edit-name').focus();
});

document.addEventListener('click', function (e) {
    const cancelBtn = e.target.closest('.cat-edit-cancel');
    if (cancelBtn) {
        const row = cancelBtn.closest('.category-row');
        row.innerHTML = row.dataset.origHtml;
        row.classList.remove('editing');
        return;
    }

    const saveBtn = e.target.closest('.cat-edit-save');
    if (!saveBtn) return;
    const row  = saveBtn.closest('.category-row');
    const id   = saveBtn.dataset.id;
    const icon = row.querySelector('.cat-edit-icon').value.trim() || '📦';
    const name = row.querySelector('.cat-edit-name').value.trim();
    if (!name) { row.querySelector('.cat-edit-name').focus(); return; }

    saveBtn.disabled = true;
    fetch('/api/projects/' + projectId + '/categories/' + id, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ name, icon }),
    })
    .then(r => r.json())
    .then(function (d) {
        if (d.error) { window.showToast(d.error, 'error'); saveBtn.disabled = false; return; }
        row.classList.remove('editing');
        row.dataset.name = name;
        row.dataset.icon = icon;
        row.innerHTML = catRowInnerHTML(id, icon, name);
        window.showToast('הקטגוריה עודכנה');
    })
    .catch(function () { window.showToast(window.sfNetError(), 'error'); saveBtn.disabled = false; });
});
})();
