// עמוד עצמאי (לא יורש מ-base.html) — escapeHtml מקומי
window.escapeHtml = window.escapeHtml || function (s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};
(function () {
    const errorBox = document.getElementById('onboardingError');
    const steps    = { 1: document.getElementById('step1'), 2: document.getElementById('step2'),
                       3: document.getElementById('step3'), 4: document.getElementById('step4') };
    const dots     = { 1: document.getElementById('dotStep1'), 2: document.getElementById('dotStep2'),
                       3: document.getElementById('dotStep3'), 4: document.getElementById('dotStep4') };

    const step0    = document.getElementById('step0');
    const stepJoin = document.getElementById('stepJoin');
    const dotsBar  = document.getElementById('onboardingDots');

    function goToStep(n) {
        errorBox.textContent = '';
        step0.style.display    = 'none';
        stepJoin.style.display = 'none';
        dotsBar.style.display  = 'flex';
        [1, 2, 3, 4].forEach(function (i) {
            steps[i].style.display = i === n ? 'block' : 'none';
            dots[i].classList.toggle('active', i <= n);
        });
    }

    function showChoice(which) {
        errorBox.textContent = '';
        [1, 2, 3, 4].forEach(function (i) { steps[i].style.display = 'none'; });
        dotsBar.style.display  = 'none';
        step0.style.display    = which === 'start' ? 'block' : 'none';
        stepJoin.style.display = which === 'join'  ? 'block' : 'none';
    }

    // ─── המזלג: משפחה חדשה או הצטרפות ───────────────────────────────────
    document.getElementById('chooseCreateBtn').addEventListener('click', () => goToStep(1));
    document.getElementById('chooseJoinBtn').addEventListener('click', function () {
        showChoice('join');
        document.getElementById('joinCode').focus();
    });
    document.getElementById('backFromJoinBtn').addEventListener('click', () => showChoice('start'));
    document.getElementById('backToChoiceBtn').addEventListener('click', () => showChoice('start'));

    const joinInput   = document.getElementById('joinCode');
    const joinPreview = document.getElementById('joinPreview');
    let previewTimer  = null;

    // תצוגה מקדימה חיה: המשתמש רואה לאיזו משפחה הוא עומד להצטרף לפני
    // שהוא מאשר, כדי שקוד שגוי ייתפס כאן ולא אחרי מעשה.
    joinInput.addEventListener('input', function () {
        const code = joinInput.value.trim();
        joinPreview.textContent = '';
        joinPreview.classList.remove('field-hint-ok', 'field-hint-bad');
        clearTimeout(previewTimer);
        if (code.replace(/[^A-Za-z0-9]/g, '').length < 6) return;

        previewTimer = setTimeout(function () {
            fetch('/api/family/preview?code=' + encodeURIComponent(code))
                .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
                .then(function (res) {
                    if (res.ok && res.data.found) {
                        joinPreview.textContent = 'מצטרפים ל: ' + res.data.name;
                        joinPreview.classList.add('field-hint-ok');
                    } else {
                        joinPreview.textContent = 'לא נמצאה משפחה עם הקוד הזה';
                        joinPreview.classList.add('field-hint-bad');
                    }
                })
                .catch(function () { /* התצוגה המקדימה היא נוחות בלבד — שקט בכשל */ });
        }, 350);
    });

    document.getElementById('joinFamilyBtn').addEventListener('click', function () {
        const code = joinInput.value.trim();
        if (!code) {
            errorBox.textContent = 'נא להזין את קוד ההזמנה';
            return;
        }
        const btn = this;
        btn.disabled = true;
        btn.textContent = 'מצטרף…';

        fetch('/api/family/join', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ code: code, confirm: true }),
        })
        .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
        .then(function (res) {
            if (!res.ok) {
                errorBox.textContent = res.data.error || 'ההצטרפות נכשלה';
                btn.disabled = false;
                btn.textContent = 'הצטרפות';
                return;
            }
            // מצטרף לא עובר onboarding — הקטגוריות של המשפחה כבר קיימות
            window.location.href = '/';
        })
        .catch(function () {
            errorBox.textContent = window.sfNetError();
            btn.disabled = false;
            btn.textContent = 'הצטרפות';
        });
    });

    document.getElementById('toStep2Btn').addEventListener('click', function () {
        if (!document.getElementById('familyName').value.trim()) {
            errorBox.textContent = 'נא להזין שם למשפחה';
            return;
        }
        goToStep(2);
    });
    document.getElementById('backTo1Btn').addEventListener('click', () => goToStep(1));
    document.getElementById('toStep3Btn').addEventListener('click', () => goToStep(3));
    document.getElementById('backTo2Btn').addEventListener('click', () => goToStep(2));
    document.getElementById('toStep4Btn').addEventListener('click', () => goToStep(4));
    document.getElementById('backTo3Btn').addEventListener('click', () => goToStep(3));

    // Copy invite code
    document.getElementById('copyInviteBtn').addEventListener('click', function () {
        const el = document.getElementById('onboardingInviteCode');
        const btn = this;
        const famEl = document.getElementById('familyName');
        const msg = window.sfInviteMessage(el.textContent.trim(),
                                           famEl && famEl.value.trim());
        window.copyToClipboard(msg, el).then(function (copied) {
            if (!copied) return;          // הודעה כבר הוצגה, והקוד מסומן
            btn.textContent = '✓ הועתקה הזמנה';
            setTimeout(function () { btn.textContent = 'העתק קוד'; }, 1800);
        });
    });

    // Category type tabs
    const typeTabs = document.querySelectorAll('.onboarding-type-tabs .toggle-btn');
    const panels   = document.querySelectorAll('.onboarding-cat-panel');
    typeTabs.forEach(function (btn) {
        btn.addEventListener('click', function () {
            typeTabs.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const type = btn.dataset.catType;
            panels.forEach(p => { p.style.display = (p.dataset.panelType === type) ? 'block' : 'none'; });
        });
    });

    // Toggle category chips on/off (multi-select, not radio)
    document.querySelectorAll('.onboarding-cat-grid').forEach(function (grid) {
        grid.addEventListener('click', function (e) {
            const btn = e.target.closest('.onboarding-cat-btn');
            if (!btn) return;
            btn.classList.toggle('active');
        });
    });

    // Add a custom category chip per type
    document.querySelectorAll('.onboarding-add-btn').forEach(function (addBtn) {
        addBtn.addEventListener('click', function () {
            const type  = addBtn.dataset.addType;
            const panel = document.querySelector(`.onboarding-cat-panel[data-panel-type="${type}"]`);
            const icon  = panel.querySelector('.onboarding-new-icon');
            const name  = panel.querySelector('.onboarding-new-name');
            const nameVal = name.value.trim();
            if (!nameVal) { name.focus(); return; }

            const grid = panel.querySelector('.onboarding-cat-grid');
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'cat-btn onboarding-cat-btn active';
            chip.dataset.name = nameVal;
            chip.dataset.icon = icon.value.trim() || '🏷';
            chip.dataset.type = type;
            chip.innerHTML = `<span class="cat-emoji">${window.escapeHtml(chip.dataset.icon)}</span><span>${window.escapeHtml(nameVal)}</span>`;
            grid.appendChild(chip);

            name.value = '';
            icon.value = '🏷';
            name.focus();
        });
    });

    // Finish: collect all active chips across all 3 types, submit
    document.getElementById('finishBtn').addEventListener('click', function () {
        const categories = Array.from(document.querySelectorAll('.onboarding-cat-btn.active')).map(btn => ({
            name: btn.dataset.name, icon: btn.dataset.icon, type: btn.dataset.type,
        }));

        if (categories.length === 0) {
            errorBox.textContent = 'נא לבחור לפחות קטגוריה אחת';
            return;
        }

        const btn = this;
        btn.disabled = true;
        btn.textContent = 'שומר…';

        fetch('/api/onboarding/complete', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                family_name: document.getElementById('familyName').value.trim(),
                categories:  categories,
                owner_attribution: {
                    expense: document.getElementById('obAttrExpense').checked,
                    income:  document.getElementById('obAttrIncome').checked,
                    savings: document.getElementById('obAttrSavings').checked,
                },
            }),
        })
        .then(r => r.json())
        .then(function (data) {
            if (data.error) {
                errorBox.textContent = data.error;
                btn.disabled = false;
                btn.textContent = 'סיום והתחלה';
                return;
            }
            window.location.href = '/';
        })
        .catch(function () {
            errorBox.textContent = window.sfNetError();
            btn.disabled = false;
            btn.textContent = 'סיום והתחלה';
        });
    });
})();
