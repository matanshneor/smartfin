(function () {

// ── אקורדיון: פתיחה/סגירה של קבוצות ──
document.querySelectorAll('.settings-group-header').forEach(function (header) {
    header.addEventListener('click', function () {
        const isOpen = header.closest('.settings-group').classList.toggle('open');
        header.setAttribute('aria-expanded', isOpen);
    });
});

// ── טאבים של סוגי קטגוריות ──
const catTabs   = document.querySelectorAll('.cat-type-tabs .toggle-btn');
const catPanels = document.querySelectorAll('.cat-tab-panel');
const newCatType = document.getElementById('newCatType');

catTabs.forEach(function (btn) {
    btn.addEventListener('click', function () {
        catTabs.forEach(function (b) {
            b.classList.remove('active');
            b.setAttribute('aria-selected', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        const tab = btn.dataset.catTab;
        catPanels.forEach(p => { p.style.display = (p.dataset.tabPanel === tab) ? '' : 'none'; });
        newCatType.value = tab;
    });
});

// ── מצב ניהול קטגוריות: חושף עריכה/מחיקה/הוספה ──
const manageBtn = document.getElementById('manageCatsBtn');
const catsArea  = document.getElementById('categoriesArea');

manageBtn.addEventListener('click', function () {
    const managing = catsArea.classList.toggle('managing');
    manageBtn.textContent = managing ? 'סיום' : 'ניהול';
    manageBtn.classList.toggle('btn-primary', managing);
    manageBtn.classList.toggle('btn-ghost', !managing);
});

// ── Family name edit ──
const nameDisplay   = document.getElementById('familyNameDisplay');
const nameEdit      = document.getElementById('familyNameEdit');
const nameInput     = document.getElementById('familyNameInput');
const editBtn       = document.getElementById('editFamilyNameBtn');
const saveBtn       = document.getElementById('saveFamilyNameBtn');
const cancelBtn     = document.getElementById('cancelFamilyNameBtn');

if (editBtn) {
    editBtn.addEventListener('click', function () {
        nameEdit.classList.add('visible');
        nameInput.focus();
    });
}

if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
        nameEdit.classList.remove('visible');
        nameInput.value = nameDisplay.textContent;
    });
}

if (saveBtn) {
    saveBtn.addEventListener('click', function () {
        const newName = nameInput.value.trim();
        if (!newName) return;
        saveBtn.disabled = true;
        fetch('/api/family', {
            method:  'PUT',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ name: newName }),
        })
        .then(r => r.json())
        .then(function (d) {
            saveBtn.disabled = false;
            if (d.status === 'ok') {
                nameDisplay.textContent = newName;
                nameEdit.classList.remove('visible');
            } else {
                window.showToast('השמירה נכשלה', 'error');
            }
        })
        .catch(function () {
            saveBtn.disabled = false;
            window.showToast('שגיאת רשת — נסה שוב', 'error');
        });
    });
}

// ── Copy invite code ──
const copyBtn    = document.getElementById('copyCodeBtn');
const inviteCode = document.getElementById('inviteCode');

if (copyBtn && inviteCode) {
    copyBtn.addEventListener('click', function () {
        navigator.clipboard.writeText(inviteCode.textContent.trim()).then(function () {
            copyBtn.textContent = '✓ הועתק';
            setTimeout(function () { copyBtn.textContent = 'העתק'; }, 2000);
        });
    });
}

// ── Join another family ──
// עד היום רגע ההרשמה היה ההזדמנות היחידה להזין קוד, ומי שנרשם לפני
// שקיבל אותו נשאר תקוע במשפחה משלו בלי דרך חזרה.
const joinBtn   = document.getElementById('joinFamilyBtn');
const joinInput = document.getElementById('joinCodeInput');
const joinError = document.getElementById('joinFamilyError');

if (joinBtn && joinInput) {
    joinBtn.addEventListener('click', function () {
        const code = joinInput.value.trim();
        joinError.textContent = '';
        if (!code) {
            joinError.textContent = 'נא להזין קוד הזמנה';
            return;
        }

        function send(confirmed) {
            return fetch('/api/family/join', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ code: code, confirm: confirmed }),
            }).then(r => r.json().then(d => ({ status: r.status, data: d })));
        }

        joinBtn.disabled = true;
        joinBtn.textContent = 'מצטרף…';

        send(false)
            .then(function (res) {
                // 409 = למשפחה הנוכחית יש תנועות, והמעבר ינתק אותן.
                // מאשרים מפורשות עם המספר לפני שממשיכים.
                if (res.status === 409 && res.data.needs_confirm) {
                    const n = res.data.transaction_count;
                    const ok = confirm(
                        `למשפחה הנוכחית שלכם יש ${n} תנועות.\n\n` +
                        'מעבר למשפחה אחרת מנתק אתכם מהן — הן יישארו במשפחה הישנה ' +
                        'ולא תוכלו לראות אותן יותר.\n\nלהמשיך?'
                    );
                    if (!ok) return null;
                    return send(true);
                }
                return res;
            })
            .then(function (res) {
                if (res === null) return;
                if (res.status >= 400) {
                    joinError.textContent = res.data.error || 'ההצטרפות נכשלה';
                    return;
                }
                window.location.reload();
            })
            .catch(function () {
                joinError.textContent = 'שגיאת רשת — נסו שוב';
            })
            .finally(function () {
                joinBtn.disabled = false;
                joinBtn.textContent = 'הצטרפות';
            });
    });
}

// ── Delete recurring transaction ──
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.delete-recurring-btn');
    if (!btn) return;
    const id  = btn.dataset.id;
    const row = btn.closest('.recurring-row');
    if (!id || !row) return;

    window.appConfirm({
        title: 'להסיר את העסקה הקבועה?',
        message: 'מופעים חדשים יפסיקו להיווצר. כל מה שכבר נרשם — כולל העסקה הראשונה — יישאר בהיסטוריה.',
        confirmText: 'הסר',
    }).then(function (ok) {
        if (!ok) return;
        // ‎/api/recurring‎ ולא ‎/api/transactions‎: זה עוצר את הסדרה ולא מוחק
        // שורה. שורת התבנית היא העסקה הראשונה בסדרה, ומחיקתה הייתה מוציאה
        // כסף אמיתי מההיסטוריה — בדיוק מה שההודעה למעלה מבטיחה שלא יקרה.
        fetch('/api/recurring/' + id, { method: 'DELETE' })
        .then(r => r.json())
        .then(function (d) {
            if (d.status === 'ok') {
                row.style.transition = 'opacity 0.25s';
                row.style.opacity = '0';
                setTimeout(() => row.remove(), 260);
                window.showToast('העסקה הקבועה הוסרה');
            } else {
                window.showToast('ההסרה נכשלה', 'error');
            }
        })
        .catch(function () { window.showToast('שגיאת רשת — נסה שוב', 'error'); });
    });
});

// ── סדר קטגוריות (▲▼) ──
function catRowInnerHTML(id, icon, name, isCustom) {
    return `
        <span class="cat-row-icon">${escapeHtml(icon)}</span>
        <span class="cat-row-name">${escapeHtml(name)}</span>
        ${isCustom ? `
        <button class="edit-cat-btn" data-id="${id}" aria-label="ערוך קטגוריה">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
            </svg>
        </button>
        <button class="delete-cat-btn" data-id="${id}" aria-label="מחק קטגוריה">✕</button>
        ` : `<span class="cat-system-badge">מובנה</span>`}
        <div class="cat-reorder-btns">
            <button type="button" class="cat-move-btn cat-move-up" data-id="${id}" aria-label="הזז למעלה">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
            </button>
            <button type="button" class="cat-move-btn cat-move-down" data-id="${id}" aria-label="הזז למטה">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
        </div>
    `;
}

function updatePanelReorderState(panel) {
    if (!panel) return;
    const rows = Array.from(panel.querySelectorAll(':scope > .category-row'));
    rows.forEach(function (row, i) {
        const up   = row.querySelector('.cat-move-up');
        const down = row.querySelector('.cat-move-down');
        if (up)   up.disabled   = (i === 0);
        if (down) down.disabled = (i === rows.length - 1);
    });
}

function persistCategoryOrder(panel) {
    const type  = panel.dataset.tabPanel;
    const order = Array.from(panel.querySelectorAll(':scope > .category-row')).map(r => r.dataset.id);
    fetch('/api/categories/reorder', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ type, order }),
    })
    .then(r => r.json())
    .then(function (d) { if (d.error) window.showToast('שמירת הסדר נכשלה', 'error'); })
    .catch(function () { window.showToast('שגיאת רשת — נסה שוב', 'error'); });
}

document.querySelectorAll('.cat-tab-panel').forEach(updatePanelReorderState);

document.addEventListener('click', function (e) {
    const btn = e.target.closest('.cat-move-up, .cat-move-down');
    if (!btn) return;
    const row   = btn.closest('.category-row');
    const panel = btn.closest('.cat-tab-panel');
    if (!row || !panel) return;
    const sibling = btn.classList.contains('cat-move-up') ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling || !sibling.classList.contains('category-row')) return;
    if (btn.classList.contains('cat-move-up')) {
        panel.insertBefore(row, sibling);
    } else {
        panel.insertBefore(sibling, row);
    }
    updatePanelReorderState(panel);
    persistCategoryOrder(panel);
});

// ── Edit category (inline) ──
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.edit-cat-btn');
    if (!btn) return;
    const row = btn.closest('.category-row');
    if (!row || row.classList.contains('editing')) return;

    const id        = btn.dataset.id;
    const origIcon  = row.dataset.icon || '📦';
    const origName  = row.dataset.name || '';

    row.classList.add('editing');
    row.dataset.origHtml = row.innerHTML;
    row.innerHTML = `
        <div class="cat-edit-form">
            <div class="add-cat-row">
                <input class="form-input emoji-input cat-edit-icon" type="text" maxlength="2">
                <input class="form-input cat-edit-name" type="text" maxlength="30">
            </div>
            <div class="edit-actions">
                <button class="btn-sm btn-primary cat-edit-save" data-id="${escapeHtml(id)}">שמור</button>
                <button class="btn-sm btn-ghost cat-edit-cancel">ביטול</button>
            </div>
        </div>
    `;
    // ערכי המשתמש נכתבים דרך .value (לא אינטרפולציה) — בטוח מ-attribute-XSS
    row.querySelector('.cat-edit-icon').value = origIcon;
    row.querySelector('.cat-edit-name').value = origName;
    row.querySelector('.cat-edit-name').focus();
});

document.addEventListener('click', function (e) {
    const cancelEditBtn = e.target.closest('.cat-edit-cancel');
    if (cancelEditBtn) {
        const row = cancelEditBtn.closest('.category-row');
        row.innerHTML = row.dataset.origHtml;
        row.classList.remove('editing');
        return;
    }

    const saveEditBtn = e.target.closest('.cat-edit-save');
    if (!saveEditBtn) return;
    const row  = saveEditBtn.closest('.category-row');
    const id   = saveEditBtn.dataset.id;
    const icon = row.querySelector('.cat-edit-icon').value.trim() || '📦';
    const name = row.querySelector('.cat-edit-name').value.trim();
    if (!name) { row.querySelector('.cat-edit-name').focus(); return; }

    saveEditBtn.disabled = true;
    fetch('/api/categories/' + id, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ name, icon }),
    })
    .then(r => r.json())
    .then(function (d) {
        if (d.error) { window.showToast(d.error, 'error'); saveEditBtn.disabled = false; return; }
        row.classList.remove('editing');
        row.dataset.name = name;
        row.dataset.icon = icon;
        row.innerHTML = catRowInnerHTML(id, icon, name, true);
        updatePanelReorderState(row.closest('.cat-tab-panel'));
        window.showToast('הקטגוריה עודכנה');
    })
    .catch(function () { window.showToast('שגיאת רשת — נסה שוב', 'error'); saveEditBtn.disabled = false; });
});

// ── Delete category ──
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.delete-cat-btn');
    if (!btn) return;
    const id  = btn.dataset.id;
    const row = btn.closest('.category-row');
    if (!id || !row) return;
    const panel = row.closest('.cat-tab-panel');

    const catName = (row.querySelector('.cat-row-name') || {}).textContent || '';
    window.appConfirm({
        title: 'למחוק את "' + catName.trim() + '"?',
        message: 'עסקאות קיימות בקטגוריה יוצגו כ"אחר".',
        confirmText: 'מחק קטגוריה',
    }).then(function (ok) {
        if (!ok) return;
        fetch('/api/categories/' + id, { method: 'DELETE' })
        .then(r => r.json())
        .then(function (d) {
            if (d.status === 'ok') {
                row.style.opacity = '0';
                row.style.height  = '0';
                row.style.overflow = 'hidden';
                row.style.transition = 'all 0.25s';
                setTimeout(function () { row.remove(); updatePanelReorderState(panel); }, 260);
                window.showToast('הקטגוריה נמחקה');
            } else {
                window.showToast('המחיקה נכשלה', 'error');
            }
        })
        .catch(function () { window.showToast('שגיאת רשת — נסה שוב', 'error'); });
    });
});

// ── Add category (הסוג נקבע לפי הטאב הפעיל) ──
const addForm  = document.getElementById('addCatForm');
const addError = document.getElementById('addCatError');

if (addForm) {
    addForm.addEventListener('submit', function (e) {
        e.preventDefault();
        addError.textContent = '';

        const icon = document.getElementById('newCatIcon').value.trim() || '🏷';
        const name = document.getElementById('newCatName').value.trim();
        const type = newCatType.value;

        if (!name) {
            addError.textContent = 'נא להזין שם קטגוריה';
            return;
        }

        const addBtn = addForm.querySelector('button[type="submit"]');
        addBtn.disabled = true;
        fetch('/api/categories', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ name, icon, type }),
        })
        .then(r => r.json())
        .then(function (cat) {
            addBtn.disabled = false;
            if (cat.error) { addError.textContent = cat.error; return; }

            const listMap = { expense: 'expenseCatList', income: 'incomeCatList', savings: 'savingsCatList' };
            const list    = document.getElementById(listMap[type]);
            if (list) {
                const li = document.createElement('li');
                li.className   = 'category-row';
                li.dataset.id  = cat.id;
                li.dataset.custom = 'true';
                li.dataset.name = cat.name;
                li.dataset.icon = cat.icon;
                li.innerHTML = catRowInnerHTML(cat.id, cat.icon, cat.name, true);
                list.appendChild(li);
                updatePanelReorderState(list);
            }

            document.getElementById('newCatName').value = '';
            document.getElementById('newCatIcon').value = '🏷';
        })
        .catch(function () {
            addBtn.disabled = false;
            addError.textContent = 'שגיאת רשת — נסה שוב';
        });
    });
}

// ── Edit account profile ──
const editProfileBtn  = document.getElementById('editProfileBtn');
const profileEdit     = document.getElementById('profileEdit');
const saveProfileBtn  = document.getElementById('saveProfileBtn');
const cancelProfileBtn = document.getElementById('cancelProfileBtn');
const profileError    = document.getElementById('profileError');
const accountNameDisplay = document.getElementById('accountNameDisplay');

if (editProfileBtn) {
    editProfileBtn.addEventListener('click', function () {
        profileEdit.classList.add('visible');
    });
}

if (cancelProfileBtn) {
    cancelProfileBtn.addEventListener('click', function () {
        profileEdit.classList.remove('visible');
        profileError.textContent = '';
    });
}

function submitProfile(workplaceScope) {
    const firstName = document.getElementById('editFirstName').value.trim();
    const lastName  = document.getElementById('editLastName').value.trim();
    const phone     = document.getElementById('editPhone').value.trim();
    const workplace = document.getElementById('editWorkplace').value.trim();

    saveProfileBtn.disabled = true;
    fetch('/api/profile', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            first_name: firstName, last_name: lastName, phone: phone, workplace: workplace,
            workplace_scope: workplaceScope || undefined,
        }),
    })
    .then(r => r.json())
    .then(function (d) {
        saveProfileBtn.disabled = false;
        if (d.error) { profileError.textContent = d.error; return; }
        accountNameDisplay.textContent = d.full_name;

        const phoneDisplay = document.getElementById('accountPhoneDisplay');
        phoneDisplay.textContent = d.phone ? '📞 ' + d.phone : '';
        phoneDisplay.style.display = d.phone ? '' : 'none';

        const workplaceDisplay = document.getElementById('accountWorkplaceDisplay');
        workplaceDisplay.textContent = d.workplace ? '💼 ' + d.workplace : '';
        workplaceDisplay.style.display = d.workplace ? '' : 'none';

        profileEdit.classList.remove('visible');
    })
    .catch(function () {
        saveProfileBtn.disabled = false;
        profileError.textContent = 'שגיאת רשת — נסה שוב';
    });
}

if (saveProfileBtn) {
    saveProfileBtn.addEventListener('click', function () {
        const firstName = document.getElementById('editFirstName').value.trim();
        const lastName  = document.getElementById('editLastName').value.trim();
        const workplaceInput = document.getElementById('editWorkplace');
        const workplace = workplaceInput.value.trim();
        profileError.textContent = '';

        if (!firstName || !lastName) {
            profileError.textContent = 'נא למלא שם פרטי ושם משפחה';
            return;
        }

        // מקום עבודה השתנה — שואלים אם להחיל גם על היסטוריית משכורות
        // או רק מהחודש הנוכחי ואילך (ראה update_workplace_history בשרת)
        const workplaceChanged = workplace !== workplaceInput.defaultValue.trim();
        if (workplaceChanged) {
            window.appConfirm({
                title: 'לעדכן גם עסקאות משכורת קודמות?',
                message: 'שינית את מקום העבודה. אפשר לעדכן אותו על כל היסטוריית המשכורות, או רק מהחודש הנוכחי ואילך (עסקאות ישנות יותר ישמרו את מקום העבודה הקודם).',
                confirmText: 'כל ההיסטוריה',
                cancelText: 'רק מהחודש הזה',
                danger: false,
            }).then(function (updateAll) {
                submitProfile(updateAll ? 'all' : 'future');
            });
        } else {
            submitProfile(null);
        }
    });
}

// ── Toggle password form ──
const togglePasswordBtn = document.getElementById('togglePasswordBtn');
const passwordForm      = document.getElementById('passwordForm');
const cancelPasswordBtn = document.getElementById('cancelPasswordBtn');

function resetPasswordForm() {
    document.getElementById('currentPassword').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('newPasswordConfirm').value = '';
    document.getElementById('passwordError').textContent = '';
    document.getElementById('passwordSuccess').textContent = '';
}

if (togglePasswordBtn) {
    togglePasswordBtn.addEventListener('click', function () {
        passwordForm.classList.toggle('visible');
    });
}

if (cancelPasswordBtn) {
    cancelPasswordBtn.addEventListener('click', function () {
        passwordForm.classList.remove('visible');
        resetPasswordForm();
    });
}

// ── Change password ──
const changePasswordBtn = document.getElementById('changePasswordBtn');
if (changePasswordBtn) {
    changePasswordBtn.addEventListener('click', function () {
        const currentPassword = document.getElementById('currentPassword').value;
        const password        = document.getElementById('newPassword').value;
        const passwordConfirm = document.getElementById('newPasswordConfirm').value;
        const pwError   = document.getElementById('passwordError');
        const pwSuccess = document.getElementById('passwordSuccess');
        pwError.textContent = '';
        pwSuccess.textContent = '';

        if (!currentPassword) {
            pwError.textContent = 'נא להזין את הסיסמה הנוכחית';
            return;
        }
        if (password.length < 6) {
            pwError.textContent = 'הסיסמה החדשה חייבת להכיל לפחות 6 תווים';
            return;
        }
        if (password !== passwordConfirm) {
            pwError.textContent = 'הסיסמאות החדשות אינן תואמות';
            return;
        }

        changePasswordBtn.disabled = true;
        changePasswordBtn.textContent = 'מעדכן…';
        fetch('/api/profile/password', {
            method:  'PUT',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                current_password: currentPassword,
                password: password,
                password_confirm: passwordConfirm,
            }),
        })
        .then(r => r.json())
        .then(function (d) {
            changePasswordBtn.disabled = false;
            changePasswordBtn.textContent = 'עדכן סיסמה';
            if (d.error) { pwError.textContent = d.error; return; }
            resetPasswordForm();
            pwSuccess.textContent = 'הסיסמה עודכנה בהצלחה';
        })
        .catch(function () {
            changePasswordBtn.disabled = false;
            changePasswordBtn.textContent = 'עדכן סיסמה';
            pwError.textContent = 'שגיאת רשת — נסה שוב';
        });
    });
}

// ── איפוס חשבון: מחיקת כל העסקאות (החשבון נשמר) ──
const toggleResetBtn  = document.getElementById('toggleResetAccountBtn');
const resetForm       = document.getElementById('resetAccountForm');
const cancelResetBtn  = document.getElementById('cancelResetAccountBtn');
const confirmResetBtn = document.getElementById('confirmResetAccountBtn');
const resetPwInput    = document.getElementById('resetAccountPassword');
const resetError      = document.getElementById('resetAccountError');
const scopeFamilyBtn  = document.getElementById('resetScopeFamily');
const scopeMineBtn    = document.getElementById('resetScopeMine');
let resetScope = 'family';

if (toggleResetBtn) {
    [scopeFamilyBtn, scopeMineBtn].forEach(function (btn) {
        btn.addEventListener('click', function () {
            scopeFamilyBtn.classList.toggle('active', btn === scopeFamilyBtn);
            scopeMineBtn.classList.toggle('active', btn === scopeMineBtn);
            resetScope = btn.dataset.scope;
        });
    });

    toggleResetBtn.addEventListener('click', function () {
        resetForm.classList.toggle('visible');
    });
    cancelResetBtn.addEventListener('click', function () {
        resetForm.classList.remove('visible');
        resetPwInput.value = '';
        resetError.textContent = '';
    });

    confirmResetBtn.addEventListener('click', function () {
        resetError.textContent = '';
        if (!resetPwInput.value) {
            resetError.textContent = 'נא להזין את הסיסמה הנוכחית';
            return;
        }
        window.appConfirm({
            title: resetScope === 'family'
                ? 'לאפס את כל עסקאות המשפחה?'
                : 'למחוק את כל העסקאות שלך?',
            message: 'פעולה זו סופית ולא ניתנת לביטול.',
            confirmText: 'אפס עסקאות',
        }).then(function (ok) {
            if (!ok) return;
            confirmResetBtn.disabled = true;
            confirmResetBtn.textContent = 'מאפס…';
            fetch('/api/account/reset', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ password: resetPwInput.value, scope: resetScope }),
            })
            .then(r => r.json())
            .then(function (d) {
                if (d.error) {
                    confirmResetBtn.disabled = false;
                    confirmResetBtn.textContent = 'אפס עסקאות';
                    resetError.textContent = d.error;
                    return;
                }
                sessionStorage.setItem('sf_toast', 'כל העסקאות נמחקו');
                window.location.href = '/';
            })
            .catch(function () {
                confirmResetBtn.disabled = false;
                confirmResetBtn.textContent = 'אפס עסקאות';
                resetError.textContent = 'שגיאת רשת — נסה שוב';
            });
        });
    });
}

// ── מחיקת חשבון לצמיתות ──
const toggleDeleteBtn  = document.getElementById('toggleDeleteAccountBtn');
const deleteForm       = document.getElementById('deleteAccountForm');
const cancelDeleteBtn  = document.getElementById('cancelDeleteAccountBtn');
const confirmDeleteBtn = document.getElementById('confirmDeleteAccountBtn');
const deletePwInput    = document.getElementById('deleteAccountPassword');
const deleteError      = document.getElementById('deleteAccountError');

if (toggleDeleteBtn) {
    toggleDeleteBtn.addEventListener('click', function () {
        deleteForm.classList.toggle('visible');
    });
    cancelDeleteBtn.addEventListener('click', function () {
        deleteForm.classList.remove('visible');
        deletePwInput.value = '';
        deleteError.textContent = '';
    });

    confirmDeleteBtn.addEventListener('click', function () {
        deleteError.textContent = '';
        if (!deletePwInput.value) {
            deleteError.textContent = 'נא להזין את הסיסמה הנוכחית';
            return;
        }
        window.appConfirm({
            title: 'למחוק את החשבון לצמיתות?',
            message: 'פעולה זו סופית ולא ניתנת לביטול — כל הנתונים שלך יימחקו.',
            confirmText: 'מחק לצמיתות',
        }).then(function (ok) {
            if (!ok) return;
            confirmDeleteBtn.disabled = true;
            confirmDeleteBtn.textContent = 'מוחק…';
            fetch('/api/account', {
                method:  'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ password: deletePwInput.value }),
            })
            .then(r => r.json())
            .then(function (d) {
                if (d.error) {
                    confirmDeleteBtn.disabled = false;
                    confirmDeleteBtn.textContent = 'מחק לצמיתות';
                    deleteError.textContent = d.error;
                    return;
                }
                window.location.href = '/login';
            })
            .catch(function () {
                confirmDeleteBtn.disabled = false;
                confirmDeleteBtn.textContent = 'מחק לצמיתות';
                deleteError.textContent = 'שגיאת רשת — נסה שוב';
            });
        });
    });
}

})();

// ── העדפות משפחה: שמירה מיידית של כל שינוי ──
(function () {
const attrSwitches   = document.querySelectorAll('[data-pref-type]');
const anomalyEnabled = document.getElementById('anomalyEnabled');
const anomalyFields  = document.getElementById('anomalyFields');
const anomalyPercent = document.getElementById('anomalyPercent');
const anomalyGap     = document.getElementById('anomalyGap');
const anomalySentence = document.getElementById('anomalySentence');
const showWorkplace  = document.getElementById('showWorkplace');
const workplaceRow   = document.getElementById('workplaceRow');
const workplaceNote  = document.getElementById('workplaceNote');
if (!anomalyEnabled) return;

function savePrefs(patch) {
    fetch('/api/family/settings', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(patch),
    })
    .then(r => r.json())
    .then(function (data) {
        if (data.error) { window.showToast(data.error, 'error'); return; }
        // המודאל הגלובלי קורא מכאן — בורר "של מי?" מתעדכן בלי רענון
        window.SF_ATTRIBUTION = data.settings.owner_attribution;
        window.showToast('ההעדפות נשמרו');
    })
    .catch(function () { window.showToast('שגיאת רשת — נסה שוב', 'error'); });
}

// דוגמה קונקרטית עם קטגוריה היפותטית של ₪1,000 בחודש — הופכת את שני
// התנאים המופשטים (אחוז + פער) למספר שקלים מוחשי אחד שקל להבין.
function updateSentence() {
    const pct = parseInt(anomalyPercent.value, 10) || 150;
    const gap = parseInt(anomalyGap.value, 10) || 0;
    const EXAMPLE_AVG = 1000;
    const threshold = Math.max(EXAMPLE_AVG * (pct / 100), EXAMPLE_AVG + gap);
    anomalySentence.textContent =
        `לדוגמה: קטגוריה שבדרך כלל עולה כ-₪${EXAMPLE_AVG.toLocaleString('en-US')} בחודש תסומן כחריגה ` +
        `רק אם ההוצאה החודש עברה ₪${Math.round(threshold).toLocaleString('en-US')}`;
}

// מקום עבודה נשען על שיוך הכנסות — בלי שיוך אין את מי להציג
const workplaceDefaultNote = workplaceNote.textContent;
function updateWorkplaceState() {
    const incomeOn = document.querySelector('[data-pref-type="income"]').checked;
    showWorkplace.disabled = !incomeOn;
    workplaceRow.classList.toggle('disabled', !incomeOn);
    workplaceNote.textContent = incomeOn ? workplaceDefaultNote : 'דורש שיוך הכנסות';
}

attrSwitches.forEach(function (sw) {
    sw.addEventListener('change', function () {
        const patch = {};
        patch[this.dataset.prefType] = this.checked;
        savePrefs({ owner_attribution: patch });
        if (this.dataset.prefType === 'income') updateWorkplaceState();
    });
});

anomalyEnabled.addEventListener('change', function () {
    anomalyFields.classList.toggle('off', !this.checked);
    savePrefs({ anomaly: { enabled: this.checked } });
});

[anomalyPercent, anomalyGap].forEach(function (inp) {
    inp.addEventListener('input', updateSentence);
    inp.addEventListener('change', function () {
        savePrefs({ anomaly: {
            percent: parseInt(anomalyPercent.value, 10) || 150,
            min_gap: parseInt(anomalyGap.value, 10) || 0,
        }});
    });
});

showWorkplace.addEventListener('change', function () {
    savePrefs({ show_workplace: this.checked });
});

updateSentence();
updateWorkplaceState();
})();

// ── פרויקטים (הגדרות): יצירה, עריכה במקום, מחיקה ──
(function () {
const newBtn    = document.getElementById('newProjectSettingsBtn');
if (!newBtn) return;
const newForm   = document.getElementById('newProjectSettingsForm');
const cancelNew = document.getElementById('cancelNewProjSettingsBtn');
const newError  = document.getElementById('newProjSettingsError');

newBtn.addEventListener('click', function () {
    newForm.style.display = newForm.style.display === 'none' ? '' : 'none';
});
cancelNew.addEventListener('click', function () {
    newForm.style.display = 'none';
    newForm.reset();
    newError.textContent = '';
    newIsPersonal = false;
    newOwnerSharedBtn.classList.add('active');
    newOwnerPersonalBtn.classList.remove('active');
});

const newOwnerSharedBtn   = document.getElementById('newProjSettingsOwnerShared');
const newOwnerPersonalBtn = document.getElementById('newProjSettingsOwnerPersonal');
let newIsPersonal = false;

[newOwnerSharedBtn, newOwnerPersonalBtn].forEach(function (btn) {
    btn.addEventListener('click', function () {
        newOwnerSharedBtn.classList.toggle('active', btn === newOwnerSharedBtn);
        newOwnerPersonalBtn.classList.toggle('active', btn === newOwnerPersonalBtn);
        newIsPersonal = btn.dataset.personal === 'true';
    });
});

newForm.addEventListener('submit', function (e) {
    e.preventDefault();
    newError.textContent = '';
    const name = document.getElementById('newProjSettingsName').value.trim();
    const budgetVal = document.getElementById('newProjSettingsBudget').value;
    const trackExpense = document.getElementById('newProjSettingsTrackExpense').checked;
    const trackIncome  = document.getElementById('newProjSettingsTrackIncome').checked;
    const trackSavings = document.getElementById('newProjSettingsTrackSavings').checked;
    if (!name) { newError.textContent = 'נא להזין שם לפרויקט'; return; }
    if (!trackExpense && !trackIncome && !trackSavings) {
        newError.textContent = 'יש לבחור לפחות סוג עסקה אחד למעקב';
        return;
    }
    const newSubmitBtn = newForm.querySelector('button[type="submit"]');
    newSubmitBtn.disabled = true;
    fetch('/api/projects', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            name: name, budget_target: budgetVal ? parseFloat(budgetVal) : null,
            is_personal: newIsPersonal,
            track_expense: trackExpense, track_income: trackIncome, track_savings: trackSavings,
        }),
    })
    .then(r => r.json())
    .then(function (data) {
        if (data.error) { newSubmitBtn.disabled = false; newError.textContent = data.error; return; }
        window.location.reload();
    })
    .catch(function () { newSubmitBtn.disabled = false; newError.textContent = 'שגיאת רשת — נסה שוב'; });
});

// ── מחיקת פרויקט ──
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.delete-project-btn');
    if (!btn) return;
    const id  = btn.dataset.id;
    const row = btn.closest('.project-settings-row');
    if (!row) return;
    const name = row.dataset.name;

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

// ── עריכת פרויקט במקום (שם/יעד/סוגי מעקב — בעלות מנוהלת רק מעמוד הפרויקט) ──
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.edit-project-settings-btn');
    if (!btn) return;
    const row = btn.closest('.project-settings-row');
    if (!row || row.classList.contains('editing')) return;

    const id = btn.dataset.id;
    const name = row.dataset.name;
    const budget = row.dataset.budgetTarget;
    const trackExpense = row.dataset.trackExpense === 'true';
    const trackIncome  = row.dataset.trackIncome === 'true';
    const trackSavings = row.dataset.trackSavings === 'true';

    row.classList.add('editing');
    row.dataset.origHtml = row.innerHTML;
    row.innerHTML = `
        <div class="cat-edit-form" style="width:100%;">
            <div class="add-cat-row">
                <input class="form-input proj-edit-name" type="text" maxlength="50">
            </div>
            <div class="form-group">
                <label class="form-label">יעד תקציב (אופציונלי)</label>
                <div class="amount-input-wrap">
                    <span class="amount-currency">₪</span>
                    <input class="form-input amount-input proj-edit-budget" type="number" min="0" step="1">
                </div>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" class="checkbox-input proj-edit-track-expense" ${trackExpense ? 'checked' : ''}>
                    <span class="checkbox-custom"></span>
                    <span class="checkbox-text">הוצאות</span>
                </label>
                <label class="checkbox-label">
                    <input type="checkbox" class="checkbox-input proj-edit-track-income" ${trackIncome ? 'checked' : ''}>
                    <span class="checkbox-custom"></span>
                    <span class="checkbox-text">הכנסות</span>
                </label>
                <label class="checkbox-label">
                    <input type="checkbox" class="checkbox-input proj-edit-track-savings" ${trackSavings ? 'checked' : ''}>
                    <span class="checkbox-custom"></span>
                    <span class="checkbox-text">חיסכון</span>
                </label>
            </div>
            <p class="form-error proj-edit-error" role="alert"></p>
            <div class="edit-actions">
                <button class="btn-sm btn-primary proj-edit-save" data-id="${escapeHtml(id)}">שמור</button>
                <button class="btn-sm btn-ghost proj-edit-cancel">ביטול</button>
            </div>
        </div>
    `;
    // ערכי המשתמש דרך .value (לא אינטרפולציה) — בטוח מ-attribute-XSS
    row.querySelector('.proj-edit-name').value = name || '';
    row.querySelector('.proj-edit-budget').value = budget || '';
    row.querySelector('.proj-edit-name').focus();
});

document.addEventListener('click', function (e) {
    const cancelBtn = e.target.closest('.proj-edit-cancel');
    if (cancelBtn) {
        const row = cancelBtn.closest('.project-settings-row');
        row.innerHTML = row.dataset.origHtml;
        row.classList.remove('editing');
        return;
    }

    const saveBtn = e.target.closest('.proj-edit-save');
    if (!saveBtn) return;
    const row = saveBtn.closest('.project-settings-row');
    const id  = saveBtn.dataset.id;
    const errorEl = row.querySelector('.proj-edit-error');
    const name = row.querySelector('.proj-edit-name').value.trim();
    const budgetVal = row.querySelector('.proj-edit-budget').value;
    const trackExpense = row.querySelector('.proj-edit-track-expense').checked;
    const trackIncome  = row.querySelector('.proj-edit-track-income').checked;
    const trackSavings = row.querySelector('.proj-edit-track-savings').checked;
    if (!name) { errorEl.textContent = 'נא להזין שם לפרויקט'; return; }
    if (!trackExpense && !trackIncome && !trackSavings) {
        errorEl.textContent = 'יש לבחור לפחות סוג עסקה אחד למעקב';
        return;
    }

    saveBtn.disabled = true;
    fetch('/api/projects/' + id, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            name, budget_target: budgetVal ? parseFloat(budgetVal) : null,
            track_expense: trackExpense, track_income: trackIncome, track_savings: trackSavings,
        }),
    })
    .then(r => r.json())
    .then(function (d) {
        if (d.error) { errorEl.textContent = d.error; saveBtn.disabled = false; return; }
        window.location.reload();
    })
    .catch(function () { errorEl.textContent = 'שגיאת רשת — נסה שוב'; saveBtn.disabled = false; });
});
})();
