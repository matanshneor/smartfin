// הליבה של הזנת עסקאות: המודאל, כפתור ה-FAB, סריקת קבלה, עריכה ומחיקה.
(function () {
    const overlay      = document.getElementById('modalOverlay');
    const fabBtn       = document.getElementById('fabBtn');
    const closeBtn     = document.getElementById('modalClose');
    const scanBtn      = document.getElementById('scanBtn');
    const scanWrapper  = document.getElementById('scannerWrapper');
    const receiptInput = document.getElementById('receiptInput');
    const txReceiptPath = document.getElementById('txReceiptPath');
    const scannerThumbnail = document.getElementById('scannerThumbnail');
    const AMOUNT_PLACEHOLDER_DEFAULT = '0.00';
    const DESCRIPTION_PLACEHOLDER_DEFAULT = 'למשל: שופרסל, משכורת…';
    const toggleExp    = document.getElementById('toggleExpense');
    const toggleInc    = document.getElementById('toggleIncome');
    const toggleSav    = document.getElementById('toggleSavings');
    const submitLabel  = document.getElementById('submitLabel');
    const submitBtn    = document.getElementById('submitBtn');
    const deleteBtn    = document.getElementById('deleteTxBtn');
    const editModeActions = document.getElementById('editModeActions');
    const duplicateBtn = document.getElementById('duplicateTxBtn');
    const categoryGrid = document.getElementById('categoryGrid');
    const projectGroup = document.getElementById('projectGroup');
    const categoryLabel = document.getElementById('categoryLabel');
    const txProject    = document.getElementById('txProject');
    const ownerGroup   = document.getElementById('ownerGroup');
    const ownerToggle  = document.getElementById('ownerToggle');
    const txOwner      = document.getElementById('txOwner');
    const recurringCb  = document.getElementById('txRecurring');
    const recurFields  = document.getElementById('recurringFields');
    const txDate       = document.getElementById('txDate');
    const txEndDate    = document.getElementById('txEndDate');
    const txFrequency  = document.getElementById('txFrequency');
    const txForm       = document.getElementById('txForm');
    const txCategory   = document.getElementById('txCategory');
    const txProjectCategory = document.getElementById('txProjectCategory');
    const txAmount     = document.getElementById('txAmount');
    const txDescription = document.getElementById('txDescription');
    const modalTitle   = document.getElementById('modalTitle');

    // שם פעולה ולא ציווי, כמו רוב הכפתורים באפליקציה ("פתיחת חשבון",
    // "יצירת פרויקט חדש", "הצטרפות"). זה גם עוקף את שאלת היחיד/רבים:
    // הטקסט שסביב מדבר ברבים ("לחצו", "הזינו"), וכפתור בציווי יחיד-זכר
    // לידו קרא כמו שני כותבים שונים.
    const TYPE_LABELS = { expense: 'הוספת הוצאה', income: 'הוספת הכנסה', savings: 'הוספת חיסכון' };
    // העדפות המשפחה: לאילו סוגי עסקאות מוצג בורר "של מי?"
    // (על window כדי שעמוד ההגדרות יעדכן את המודאל מיד עם שינוי העדפה)
    window.SF_ATTRIBUTION = window.SF_PAGE_DATA.attribution || {};
    const OWNER_LABELS = { expense: 'של מי ההוצאה?', income: 'של מי ההכנסה?', savings: 'של מי החיסכון?' };

    let currentType   = 'expense';
    let editId        = null;   // null = adding a new transaction, otherwise editing this id
    let editingRecurringParentId = null; // אם עורכים מופע שנוצר מתבנית קבועה — מזהה התבנית
    // נפתח מ"עסקאות קבועות" בהגדרות: השינוי חל מהחודש הנוכחי (מתן, 2.10)
    let editingSeries = false;
    let editingOriginal = null;          // העסקה כמו שהייתה לפני העריכה — ל"בטל" (סבב 6, פריט 10)
    let originalAmount = null;  // הסכום שנטען לעריכה, להשוואה לזיהוי "שיניתם את הסכום"
    let categoriesCache = null;

    /* סריקת קבלה לוקחת כמה שניות, ובזמן הזה אפשר לסגור את הטופס ולפתוח עסקה
     * אחרת. התשובה נכתבה לטופס שפתוח **בזמן שהיא חוזרת** — כלומר לתוך עסקה
     * קיימת שנפתחה לתיקון: סכום, תיאור, תאריך וקטגוריה הוחלפו, והקבלה הוצמדה.
     *
     * ‎scanSeq‎ עולה בכל סריקה ובכל סגירה/פתיחה של הטופס; תשובה שהמספר שלה
     * כבר לא הנוכחי לא נוגעת בכלום. ‎claimedReceipt‎ הוא הקבלה ששמירה כבר
     * לקחה — כדי שסגירת החלון אחרי "שמור" (שבדף הבית קורית לפני שהשרת ענה)
     * לא תמחק אותה. */
    let scanSeq = 0;
    let claimedReceipt = null;

    /* בדף הבית החלון נסגר ב"שמור" לפני שהשרת ענה, כדי שההוספה תרגיש מיידית.
     * מי שמוסיף כמה עסקאות ברצף כבר פותח + ומקליד את הבאה כשהתשובה חוזרת —
     * והיא סגרה את החלון **שלו**, ומה שהקליד נמחק. ‎formSeq‎ עולה בכל פתיחה
     * של הטופס; שמירה שהטופס שלה כבר הוחלף לא נוגעת בטופס הנוכחי. */
    let formSeq = 0;

    // תמונה שהועלתה לסריקה ולא נשמרה עם עסקה. השרת מוחק רק מה שאף עסקה
    // לא מצביעה עליו; כשל כאן לא מעניין את המשתמש — הכי גרוע, נשאר קובץ.
    function discardReceipt(path) {
        if (!path || path === claimedReceipt) return;
        fetch('/api/receipts/discard', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ path: path }),
        }).catch(function () {});
    }
    let membersCache  = null;
    let projectsCache = null;
    let projectCategoriesCache = {}; // מפתח: "<projectId>:<type>"
    let categoryGridIsProject = false; // האם רשת הקטגוריות הנוכחית מציגה קטגוריות פרויקט או משפחה

    // תאריך לפי השעון המקומי (לא UTC) עם היסט אופציונלי בימים — אחרת בין
    // חצות ל~03:00 בישראל היה יוצא תאריך של אתמול.
    function dateStr(offsetDays) {
        const d = new Date();
        if (offsetDays) d.setDate(d.getDate() + offsetDays);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }
    function todayStr() { return dateStr(0); }

    // תאריך ההתחלה של עסקה חדשה: היום — או, בעמוד של חודש אחר, אותו יום
    // בתוך החודש ההוא (ה-31 בפברואר נקצץ לסוף החודש). ראו month.html.
    function defaultTxDate() {
        const main = document.querySelector('main[data-default-month]');
        const ym = main && main.dataset.defaultMonth;
        if (!ym || !/^\d{4}-\d{2}$/.test(ym)) return todayStr();
        const year = parseInt(ym.slice(0, 4), 10), month = parseInt(ym.slice(5, 7), 10);
        const lastDay = new Date(year, month, 0).getDate();
        const day = Math.min(new Date().getDate(), lastDay);
        return ym + '-' + String(day).padStart(2, '0');
    }

    // צ'יפים "היום"/"אתמול" — קיצור לבחירת התאריך הנפוץ בלי בורר
    // ‎.date-quick-chips‎ ולא כל ‎.date-chip‎: כפתורי הסינון בעמוד החודש לובשים
    // את אותו עיצוב, ולחיצה עליהם שינתה את התאריך בטופס וסימנה אותם כפעילים
    // ‎.is-edit‎ על החלון: בעריכה אין היום/אתמול/שלשום — רק התאריך (מתן, 5.10)
    const modalSheetEl = overlay.querySelector('.modal-sheet');
    const datePick     = document.querySelector('.date-pick');
    const datePickText = document.getElementById('datePickText');
    const HE_LONG_DATE = new Intl.DateTimeFormat('he-IL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

    function setEditLook(isEdit) {
        if (modalSheetEl) modalSheetEl.classList.toggle('is-edit', isEdit);
        syncDateChips();
    }

    function syncDateChips() {
        let quick = false;
        document.querySelectorAll('.date-quick-chips .date-chip').forEach(function (chip) {
            const on = dateStr(parseInt(chip.dataset.days, 10)) === txDate.value;
            chip.classList.toggle('active', on);
            quick = quick || on;
        });
        if (!datePickText) return;
        const d = /^\d{4}-\d{2}-\d{2}$/.test(txDate.value) ? new Date(txDate.value + 'T00:00:00') : null;
        const editing = modalSheetEl && modalSheetEl.classList.contains('is-edit');
        // בעריכה — התאריך המלא. בהוספה — "תאריך אחר", או התאריך עצמו כשנבחר כזה
        datePickText.textContent = !d ? 'תאריך אחר'
            : editing ? HE_LONG_DATE.format(d)
            : quick ? 'תאריך אחר' : d.getDate() + '.' + (d.getMonth() + 1);
        if (datePick) datePick.classList.toggle('active', !editing && !!d && !quick);
    }
    // במחשב נגיעה בשדה השקוף לא פותחת את הבורר (רק החץ שלו) — פותחים ידנית
    txDate.addEventListener('click', function () {
        try { if (txDate.showPicker) txDate.showPicker(); } catch (e) { /* הבורר הרגיל */ }
    });
    document.querySelectorAll('.date-quick-chips .date-chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            txDate.value = dateStr(parseInt(chip.dataset.days, 10));
            syncDateChips();
        });
    });
    txDate.addEventListener('change', syncDateChips);

    /* ההגדרות ועמוד עריכת הפרויקט משנים קטגוריות בלי לעזוב את העמוד. המטמון
     * כאן לא ידע על זה: קטגוריה שנוספה לא הופיעה ב-+, ושנמחקה — הופיעה,
     * ונכשלה בשמירה. */
    window.sfForgetCategories = function () {
        categoriesCache = null;
        projectCategoriesCache = {};
    };

    function loadCategories() {
        if (categoriesCache) return Promise.resolve(categoriesCache);
        return window.sfFetchList('/api/categories')
            .then(function (cats) { categoriesCache = cats; return cats; });
    }

    function loadMembers() {
        if (membersCache) return Promise.resolve(membersCache);
        return window.sfFetchList('/api/family/members')
            .then(function (members) { membersCache = members; return members; });
    }

    function loadProjects() {
        if (projectsCache) return Promise.resolve(projectsCache);
        // גם פרויקטים שהסתיימו, מסומנים — עסקה ישנה בהם שנערכת נשארת בהם
        return window.sfFetchList('/api/projects?include_archived=1')
            .then(function (projects) { projectsCache = projects; return projects; });
    }

    function loadProjectCategories(projectId, type) {
        const key = projectId + ':' + type;
        if (projectCategoriesCache[key]) return Promise.resolve(projectCategoriesCache[key]);
        return window.sfFetchList('/api/projects/' + projectId + '/categories?type=' + type)
            .then(function (cats) { projectCategoriesCache[key] = cats; return cats; });
    }

    // מקור הקטגוריות תלוי בבחירת פרויקט: אם נבחר פרויקט — הקטגוריות הייעודיות
    // שלו; אחרת — קטגוריות המשפחה הרגילות לפי סוג העסקה הנוכחי.
    function refreshCategoryGrid(selectedId, keepOriginal) {
        const projectId = txProject.value;
        // מאיפה הקטגוריות — הבחירה בפרויקט יושבת רחוק מתחת
        const chosen = projectId && txProject.options[txProject.selectedIndex];
        categoryLabel.textContent = chosen ? 'קטגוריה בפרויקט "' + chosen.textContent + '"' : 'קטגוריה';
        if (projectId) {
            const forType = currentType;
            loadProjectCategories(projectId, forType).then(function (cats) {
                // אם המשתמש החליף פרויקט/סוג בזמן הטעינה — לא לדרוס את הרשת
                // עם תוצאה של בקשה ישנה (מירוץ out-of-order).
                if (txProject.value !== projectId || currentType !== forType) return;
                renderCategoryGrid(cats, selectedId, true, keepOriginal);
            });
        } else {
            const cats = (categoriesCache || []).filter(c => c.type === currentType);
            renderCategoryGrid(cats, selectedId, false, keepOriginal);
        }
    }

    function renderCategoryGrid(cats, selectedId, isProject, keepOriginal) {
        categoryGridIsProject = isProject;
        categoryGrid.innerHTML = '';
        // הקטגוריה הנוכחית לא ברשת (של סוג שהפרויקט כבר לא עוקב אחריו):
        // כפתור משלה, בחור — במקום לבחור בשבילו את הראשונה. "ללא קטגוריה"
        // כבר לא אפשרות: אין עסקה בלי קטגוריה (test_category_required).
        const keepCurrent = keepOriginal && !!selectedId && !cats.some(c => c.id === selectedId);
        if (keepCurrent) {
            cats = [{ id: selectedId, type: currentType, icon: '•',
                      name: 'הקטגוריה הנוכחית' }].concat(cats);
        }
        if (!cats.length) {
            const empty = document.createElement('p');
            empty.className = 'cat-grid-empty';
            empty.textContent = isProject
                ? 'לפרויקט אין עדיין קטגוריות במחלקה הזאת — אפשר להוסיף בעריכת הפרויקט'
                : 'אין עדיין קטגוריות במחלקה הזאת — אפשר להוסיף בהגדרות';
            categoryGrid.appendChild(empty);
        }
        // הסדר נקבע בשרת (sort_order) — כולל מיקום "אחר", שניתן להזזה בהגדרות
        cats.forEach(function (cat) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'cat-btn';
            btn.dataset.value = cat.id;
            btn.dataset.type = cat.type;
            btn.innerHTML = `<span class="cat-emoji">${escapeHtml(cat.icon)}</span><span>${escapeHtml(cat.name)}</span>`;
            btn.setAttribute('role', 'radio');
            btn.setAttribute('aria-checked', 'false');
            categoryGrid.appendChild(btn);
        });
        // ברירת מחדל: בהכנסה נבחרת "משכורת" אם קיימת (בלי תלות בסדר
        // התצוגה); בכל שאר המצבים — הקטגוריה הראשונה.
        let fallbackBtn = categoryGrid.querySelector('.cat-btn');
        if (!selectedId && currentType === 'income') {
            const salary = cats.find(c => c.name && c.name.indexOf('משכורת') !== -1);
            const salaryBtn = salary && categoryGrid.querySelector(`[data-value="${salary.id}"]`);
            if (salaryBtn) fallbackBtn = salaryBtn;
        }
        const toSelect = keepCurrent
            ? categoryGrid.querySelector('.cat-btn')
            : ((selectedId && categoryGrid.querySelector(`[data-value="${selectedId}"]`)) || fallbackBtn);
        txCategory.value = '';
        txProjectCategory.value = '';
        if (toSelect) {
            toSelect.classList.add('active');
            toSelect.setAttribute('aria-checked', 'true');
            if (isProject) txProjectCategory.value = toSelect.dataset.value;
            else txCategory.value = toSelect.dataset.value;
        }
    }

    function buildOwnerToggle(selectedOwner, keepOriginal) {
        // "משותפת" ראשונה ברשימה כדי שתופיע מימין (RTL: הפריט הראשון ב-DOM מוצג בצד ימין)
        const options = [{ value: 'shared', label: 'משותפת' }]
            .concat((membersCache || []).map(m => ({ value: m.id, label: m.name })));
        // מי שעבר למשפחה אחרת כבר לא ברשימה — ובלי זה העסקה שלו הפכה
        // ל"משותפת" בכל עריכה. השרת מקבל בעלים שלא השתנה.
        if (keepOriginal && selectedOwner && !options.some(o => o.value === selectedOwner)) {
            options.push({ value: selectedOwner, label: 'בן משפחה לשעבר' });
        }
        ownerToggle.innerHTML = '';
        options.forEach(function (opt) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'owner-btn';
            btn.dataset.value = opt.value;
            btn.textContent = opt.label;
            btn.setAttribute('role', 'radio');
            btn.setAttribute('aria-checked', 'false');
            ownerToggle.appendChild(btn);
        });
        // ברירת מחדל: "משותפת" (רלוונטי כשמוסיפים עסקה חדשה ואין עדיין
        // שיוך קיים לשמר) — לא בן המשפחה הראשון ברשימה
        const toSelect = (selectedOwner && ownerToggle.querySelector(`[data-value="${selectedOwner}"]`))
            || ownerToggle.querySelector('[data-value="shared"]')
            || ownerToggle.querySelector('.owner-btn');
        if (toSelect) {
            toSelect.classList.add('active');
            toSelect.setAttribute('aria-checked', 'true');
            txOwner.value = toSelect.dataset.value;
        }
    }

    function buildProjectSelect(selectedProjectId, keepOriginal) {
        const trackKey = { expense: 'track_expense', income: 'track_income', savings: 'track_savings' }[currentType];
        // פרויקט שהפסיק לעקוב אחרי הסוג לא מוצע לעסקה חדשה — אבל עסקה שכבר
        // בו נשארת בו. אחרת עריכת הסכום שלה הוציאה אותה אל הוצאות הבית.
        // פרויקט שהסתיים לא מוצע לעסקה חדשה — רק עסקה שכבר בו נשארת בו
        const projects = (projectsCache || []).filter(p => (p[trackKey] && !p.archived)
            || (keepOriginal && p.id === selectedProjectId));

        // השדה מוסתר כשאין לאן לשייך.
        //
        // הוא ישב במקום ה**שני** במודאל, מיד אחרי הסכום, ומשפחה בלי
        // פרויקטים ראתה תפריט נפתח עם אפשרות אחת: "ללא". זו הפעולה
        // שאדם עושה הכי הרבה באפליקציה, והשדה הראשון שהוא פוגש בה היה
        // שדה שלא רלוונטי לו.
        //
        // בורר "של מי?" ממש מתחתיו כבר עושה בדיוק את זה (ראו ‎ownerGroup‎
        // ב-‎setType‎) — הדפוס היה קיים ולא הוחל כאן.
        projectGroup.style.display = projects.length ? '' : 'none';
        if (!projects.length) { txProject.value = ''; return; }

        txProject.innerHTML = '<option value="">ללא</option>' +
            projects.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join('');
        txProject.value = projects.some(p => p.id === selectedProjectId) ? selectedProjectId : '';
    }

    let modalLastFocused = null;
    let resetSheetDrag = function () {};   // נקבע עם המשיכה לסגירה, למטה

    function openModal() {
        resetSheetDrag();
        loadDescriptions();
        hideSuggest();
        modalLastFocused = document.activeElement;
        overlay.classList.add('open');
        document.body.style.overflow = 'hidden';
        // בפריים הבא: המודאל מוסתר ב-visibility כשהוא סגור (כדי שלא יהיה
        // ב-tab order ובקורא המסך), ואי אפשר למקד אלמנט בתוך אב מוסתר.
        // המיקוד באותו פריים שבו נוספה המחלקה היה נבלע בשקט.
        requestAnimationFrame(function () { txAmount.focus(); });
    }

    // כל האלמנטים הניתנים למיקוד בתוך המודאל הפתוח כרגע — מחושב כל פעם
    // מחדש כי התוכן (שדות, כפתור מחיקה) משתנה בין הוספה לעריכה
    function getModalFocusables() {
        return Array.prototype.slice.call(
            // [tabindex] נכלל כי כפתור השמירה הוא <label role="button">;
            // tabindex="-1"/aria-hidden מסוננים כדי שמלכודת הפוקוס לא תנחת
            // על הפקדים הנסתרים (מתג ה-haptic, כפתור ה-submit לגיבוי)
            overlay.querySelectorAll('button, input, select, textarea, a[href], [tabindex]')
        ).filter(function (el) {
            return el.offsetParent !== null
                && !el.disabled
                && el.getAttribute('tabindex') !== '-1'
                && el.getAttribute('aria-hidden') !== 'true';
        });
    }

    function resetScanUI() {
        // ‎txReceiptPath‎ **חייב** להתאפס כאן ולא רק ב-‎resetForm‎.
        // ‎closeModal‎ קורא לכאן בלבד, ו-‎resetForm‎ רץ רק מ-‎openAddModal‎ —
        // אז סריקה שננטשה (✕ במקום שמירה) השאירה את הנתיב בשדה, והעריכה
        // הבאה של **עסקה קיימת** שלחה אותו וקיבלה קבלה של מישהו אחר.
        // גרוע מזה: שתי שורות שמצביעות על אותו קובץ, ומחיקת אחת מוחקת
        // את הקובץ של השנייה.
        txReceiptPath.value = '';
        scanWrapper.classList.remove('active');
        scanBtn.disabled = false;
        scanBtn.querySelector('.scan-btn-text').textContent = 'סריקת קבלה';
        receiptInput.value = '';
        if (scannerThumbnail.src) {
            URL.revokeObjectURL(scannerThumbnail.src);
            scannerThumbnail.removeAttribute('src');
        }
        txAmount.placeholder = AMOUNT_PLACEHOLDER_DEFAULT;
        txDescription.placeholder = DESCRIPTION_PLACEHOLDER_DEFAULT;
    }

    function closeModal() {
        overlay.classList.remove('open');
        document.body.style.overflow = '';
        scanSeq++;                              // סריקה שעוד רצה — כבר לא של אף טופס
        discardReceipt(txReceiptPath.value);    // נסרקה ולא נשמרה
        resetScanUI();
        formError.textContent = '';
        if (modalLastFocused) { modalLastFocused.focus(); modalLastFocused = null; }
        refreshIfPending();
    }

    function resetForm() {
        txForm.reset();
        txDate.value = defaultTxDate();
        txReceiptPath.value = '';
        formError.textContent = '';
        recurFields.classList.remove('visible');
        resetScanUI();
        syncDateChips();
    }

    function updateSubmitLabel() {
        if (editId) { submitLabel.textContent = 'שמירת השינויים'; return; }
        submitLabel.textContent = TYPE_LABELS[currentType];
    }

    /* ‎keepOriginal‎: מילוי ראשון של טופס עריכה. ערך שכבר רשום על העסקה נשמר
     * גם כשהוא לא ברשימת האפשרויות — עסקה בלי קטגוריה, של מי שעבר למשפחה
     * אחרת, או בפרויקט שהפסיק לעקוב אחרי הסוג. עד היום הטופס בחר במקומו
     * (הקטגוריה הראשונה, "משותפת", "ללא"), ושמירה של שינוי בסכום שינתה גם
     * אותם, בשקט. כשהמשתמש מחליף סוג בעצמו — ‎keepOriginal‎ כבוי. */
    function setType(type, selectedCategoryId, selectedOwner, selectedProjectId, keepOriginal) {
        currentType = type;
        toggleExp.classList.toggle('active', type === 'expense');
        toggleInc.classList.toggle('active', type === 'income');
        toggleSav.classList.toggle('active', type === 'savings');
        toggleExp.setAttribute('aria-pressed', type === 'expense');
        toggleInc.setAttribute('aria-pressed', type === 'income');
        toggleSav.setAttribute('aria-pressed', type === 'savings');
        const modalSheet = document.querySelector('.modal-sheet');
        modalSheet.classList.toggle('income-mode', type === 'income');
        modalSheet.classList.toggle('expense-mode', type === 'expense');
        modalSheet.classList.toggle('savings-mode', type === 'savings');
        buildProjectSelect(selectedProjectId, keepOriginal);
        refreshCategoryGrid(selectedCategoryId, keepOriginal);
        // בורר "של מי?" מופיע רק בסוגים שהמשפחה הפעילה בהם שיוך (העדפות משפחה),
        // ולא כשבמשפחה אדם אחד (מתן, 5.10). אז הוא רק מוסתר: הבחירה נבנית
        // ונשלחת כמו תמיד — בלעדיה השרת היה רושם על המחובר עסקה שהייתה משותפת.
        const hasOwner = !!window.SF_ATTRIBUTION[type];
        ownerGroup.style.display = (hasOwner && !window.SF_PAGE_DATA.singleMember) ? '' : 'none';
        if (hasOwner) {
            document.getElementById('ownerLabel').textContent = OWNER_LABELS[type];
            buildOwnerToggle(selectedOwner, keepOriginal);
        }
        // סריקת קבלה קיימת רק בהוספת הוצאה חדשה — לא בעריכה ולא בהכנסה/חיסכון
        scanBtn.style.display = (!editId && type === 'expense') ? '' : 'none';
        updateSubmitLabel();
    }

    // מציג משוב טעינה עדין על האלמנט שפתח את המודאל (FAB/שורת עסקה) —
    // בלי זה, בחיבור איטי נראה כאילו הלחיצה לא הגיבה עד שהמודאל נפתח
    function withLoadingTrigger(el, promise) {
        if (el) el.classList.add('is-loading-trigger');
        return promise.finally(function () {
            if (el) el.classList.remove('is-loading-trigger');
        });
    }

    /* נועל את תיבת "עסקה קבועה" על מופע שכבר שייך לסדרה, ומסביר למה.
     * בלי זה הסימון נראה זמין לגמרי, והלחיצה עליו — קריאה סבירה של
     * "שיהיה קבוע מעכשיו" — הייתה מייצרת סדרה כפולה. */
    function setRecurringLock(locked) {
        recurringCb.disabled = locked;
        const group = recurringCb.closest('.recurring-group');
        if (group) group.classList.toggle('is-locked', locked);
        let note = document.getElementById('recurringLockNote');
        if (locked && !note && group) {
            note = document.createElement('p');
            note.id = 'recurringLockNote';
            note.className = 'field-hint';
            note.textContent = 'זו עסקה קבועה. '
                             + 'לשינוי שלה מהחודש הנוכחי והלאה — הגדרות ← עסקאות קבועות.';
            group.appendChild(note);
        } else if (!locked && note) {
            note.remove();
        }
    }

    function openAddModal() {
        scanSeq++;
        formSeq++;
        setSubmitBusy(false);                   // טופס חדש לא "באמצע שמירה" — ראו ‎finish‎
        editId = null;
        editingRecurringParentId = null;
        editingSeries = false;
        originalAmount = null;
        modalTitle.textContent = 'הוספת עסקה';
        setEditLook(false);
        editModeActions.style.display = 'none';
        if (enteredMeta) enteredMeta.hidden = true;
        setRecurringLock(false);
        resetForm();
        const mySeq = formSeq;
        withLoadingTrigger(fabBtn, Promise.all([loadCategories(), loadMembers(), loadProjects()]))
            .then(function () {
                if (mySeq !== formSeq) return;      // נלחצה בינתיים עסקה — היא קובעת
                // בעמוד פרויקט: הפרויקט כבר בחור, והסוג הוא סוג שהוא עוקב
                // אחריו — פרויקט של הכנסות בלבד לא נפתח על "הוצאה" (רעיון 8)
                const here = document.getElementById('sfPageProject');
                const project = here && (projectsCache || [])
                    .find(function (p) { return p.id === here.dataset.projectId && !p.archived; });
                const type = !project || project.track_expense ? 'expense'
                           : project.track_income ? 'income' : 'savings';
                setType(type, undefined, undefined, project ? project.id : undefined);
                openModal();
            })
            .catch(function () {
                if (mySeq === formSeq) window.showToast(window.sfNetError(), 'error');
            });
    }

    // ── "הוזנה ע״י אור · אתמול 18:32" בתחתית חלון העריכה (מתן, 3.10) ──
    const enteredMeta = document.getElementById('txEnteredMeta');
    function loadEnteredMeta(id) {
        if (!enteredMeta) return;
        enteredMeta.hidden = true;
        enteredMeta.textContent = '';
        const mySeq = formSeq;
        fetch('/api/transactions/' + encodeURIComponent(id) + '/meta', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) {
                // בינתיים נפתח טופס אחר — השורה לא שלו
                if (mySeq !== formSeq || !d || !d.text) return;
                enteredMeta.textContent = d.text;
                enteredMeta.hidden = false;
            })
            .catch(function () { /* שורת מידע — בלעדיה החלון עובד כרגיל */ });
    }

    function openEditModal(tx, triggerEl) {
        scanSeq++;
        formSeq++;
        setSubmitBusy(false);                   // טופס חדש לא "באמצע שמירה" — ראו ‎finish‎
        txReceiptPath.value = '';               // לא יורשים קבלה מטופס קודם
        editId = tx.id;
        editingRecurringParentId = tx.recurringParentId || null;
        editingSeries = !!(triggerEl && triggerEl.closest && triggerEl.closest('#recurringList'));
        editingOriginal = tx;
        originalAmount = parseFloat(tx.amount);
        modalTitle.textContent = 'עריכת עסקה';
        setEditLook(true);
        editModeActions.style.display = 'flex';
        loadEnteredMeta(tx.id);
        formError.textContent = '';

        /* הלחיצה האחרונה קובעת. הטופס מתמלא רק כשהרשימות מגיעות, ו-‎editId‎
         * נקבע כבר עכשיו — אז לחיצה על א' ומיד על ב' ברשת איטית מילאה את
         * הטופס בנתונים של א' ושמרה אותם על ב'. ועסקה ומיד + מילאה את טופס
         * "עסקה חדשה" בנתונים שלה — ושמירה יצרה עותק. */
        const mySeq = formSeq;
        withLoadingTrigger(triggerEl, Promise.all([loadCategories(), loadMembers(), loadProjects()]))
            .then(function () {
                if (mySeq !== formSeq) return;
                const selectedCategoryId = tx.projectId ? tx.projectCategoryId : tx.categoryId;
                setType(tx.type, selectedCategoryId, tx.userId || 'shared', tx.projectId, true);

                txAmount.value       = plainAmount(tx.amount);
                txDescription.value  = tx.description || '';
                txDate.value         = tx.date;
                syncDateChips();
                recurringCb.checked  = tx.isRecurring;
                recurFields.classList.toggle('visible', tx.isRecurring);
                if (tx.isRecurring) {
                    txFrequency.value = tx.recurringFrequency || 'monthly_1';
                    txEndDate.value   = tx.recurringEndDate || '';
                }
                // מופע שכבר נוצר מסדרה: סימון "קבועה" עליו היה מייצר
                // תבנית שנייה שרצה במקביל לראשונה. השרת חוסם את זה
                // ממילא — כאן פשוט לא מציעים פעולה שתיכשל.
                setRecurringLock(!!tx.recurringParentId);
                updateSubmitLabel();
                openModal();
            })
            .catch(function () {
                if (mySeq === formSeq) window.showToast(window.sfNetError(), 'error');
            });
    }

    fabBtn.addEventListener('click', openAddModal);

    // חימום המטמון בדף הבית: הקטגוריות ובני המשפחה נמשכים ברקע אחרי
    // שהדף התייצב, כדי שגם הפתיחה הראשונה של כרטיסייה תהיה מיידית.
    if (document.querySelector('.transactions-list')) {
        const warm = function () { loadCategories(); loadMembers(); };
        if ('requestIdleCallback' in window) requestIdleCallback(warm, { timeout: 2500 });
        else setTimeout(warm, 1200);
    }

    // פתיחה אוטומטית של מודל ההוספה דרך קיצור ה-PWA "הוסף עסקה" (‎/?add=1‎).
    // מנקים את הפרמטר מה-URL כדי שרענון לא יפתח שוב את המודל.
    if (new URLSearchParams(window.location.search).get('add') === '1') {
        history.replaceState(null, '', window.location.pathname);
        openAddModal();
    }

    closeBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });

    // Escape סוגר את המודאל, Tab/Shift+Tab נשארים בתוכו (focus trap)
    overlay.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { closeModal(); return; }
        if (e.key !== 'Tab') return;
        const focusables = getModalFocusables();
        if (!focusables.length) return;
        const first = focusables[0];
        const last  = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });

    // תנועה פיזיקלית משותפת — ב-core.js
    const sfSpring = window.sfSpring, sfProject = window.sfProject,
          sfRubber = window.sfRubber, sfVelocity = window.sfVelocity;

    /* ── משיכה למטה סוגרת את החלון (מתן, 7.10 — עיצוב בנוסח אפל, סעיף 1) ──
     *
     * הידית שבראש החלון לא עשתה כלום, ובאייפון כל חלון כזה נסגר במשיכה.
     * החלון זז עם האצבע אחד-לאחד. בעזיבה ההחלטה לפי **לאן התנועה הולכת**
     * ולא רק איפה היא נעצרה: המהירות מוטלת קדימה (הנוסחה של אפל לגלילה),
     * אז הנפה קצרה ומהירה סוגרת, וגרירה ארוכה ואיטית שחוזרת למעלה — לא.
     * למעלה מהמקום הוא מתנגד בהדרגה במקום להיעצר בבת אחת.
     *
     * האנימציה אחרי העזיבה היא קפיץ שממשיך במהירות של האצבע, בלי תפר
     * בין הגרירה לתנועה. ונגיעה בחלון באמצע החזרה תופסת אותו מהמקום שבו
     * הוא באמת נמצא. */
    (function () {
        const sheet = modalSheetEl;
        if (!sheet) return;
        const SCRIM = 0.6;                       // השקיפות של הרקע הכהה, כמו ב-‎.modal-overlay‎
        const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        let y = 0, anim = null, cleanup = 0, g = null;

        function paint(v) {
            y = v;
            sheet.style.transform = 'translateY(' + v + 'px)';
            const p = Math.min(Math.max(v / sheet.offsetHeight, 0), 1);
            overlay.style.backgroundColor = 'rgba(20, 16, 7, ' + (SCRIM * (1 - p)).toFixed(3) + ')';
        }
        function clearInline() {
            sheet.style.transition = sheet.style.transform = '';
            overlay.style.backgroundColor = '';
            y = 0;
        }
        function stop() {
            if (anim) { anim(); anim = null; }
            clearTimeout(cleanup); cleanup = 0;
        }
        // חלון שנפתח מחדש מתחיל נקי, גם אם הסגירה הקודמת עוד לא סיימה לנקות
        resetSheetDrag = function () { stop(); clearInline(); };

        function spring(to, v0, response, damping, done, until) {
            stop();
            anim = sfSpring(y, to, v0, response, damping, paint,
                            function () { anim = null; done(); }, until);
        }

        function snapBack(v) {
            if (calm) { stop(); clearInline(); return; }
            spring(0, v, 0.3, 0.8, clearInline);
        }
        function dismiss(v) {
            const h = sheet.offsetHeight;
            function offScreen() {
                closeModal();
                // הרקע דוהה עכשיו; החלון כבר מחוץ למסך. אחרי הדעיכה מחזירים
                // אותו בשקט למצב הסגור של ה-CSS, בלי שתיראה תנועה.
                cleanup = setTimeout(function () {
                    cleanup = 0;
                    clearInline();
                    sheet.style.transition = 'none';
                    void sheet.offsetHeight;          // נקבע בלי מעבר, ורק אז המעבר חוזר
                    sheet.style.transition = '';
                }, 300);
            }
            if (calm) { offScreen(); return; }
            spring(h + 40, Math.max(v, 600), 0.3, 1, offScreen, function (x) { return x >= h; });
        }

        overlay.addEventListener('touchstart', function (e) {
            if (!overlay.classList.contains('open') || e.touches.length !== 1) return;
            if (!sheet.contains(e.target)) return;
            const t = e.touches[0];
            g = { x0: t.clientX, y0: t.clientY, from: 0, axis: null, samples: [] };
            if (anim) {
                // תפיסה באמצע תנועה: ממשיכים מהמקום שבו החלון באמת נמצא
                stop();
                g.axis = 'y';
                g.from = y;
                sheet.style.transition = 'none';
            }
            g.samples.push({ t: e.timeStamp, p: t.clientY });
        }, { passive: true });

        overlay.addEventListener('touchmove', function (e) {
            if (!g) return;
            const t = e.touches[0];
            const dx = t.clientX - g.x0, dy = t.clientY - g.y0;
            if (!g.axis) {
                if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
                // הצידה (פסי הקטגוריות), למעלה, או חלון שגלול פנימה — זו
                // גלילה רגילה, לא משיכה
                if (Math.abs(dx) > Math.abs(dy) || dy < 0 || sheet.scrollTop > 0) { g = null; return; }
                g.axis = 'y';
                g.y0 += 8;                          // בלי קפיצה של 8 הפיקסלים של ההחלטה
                sheet.style.transition = 'none';
            }
            e.preventDefault();                    // החלון זז, לא התוכן שבתוכו
            const raw = g.from + t.clientY - g.y0;
            paint(raw >= 0 ? raw : sfRubber(raw, sheet.offsetHeight));
            g.samples.push({ t: e.timeStamp, p: t.clientY });
            if (g.samples.length > 6) g.samples.shift();
        }, { passive: false });

        function release(e, cancelled) {
            if (!g) return;
            const dragged = g.axis === 'y';
            const s = g.samples;
            g = null;
            if (!dragged) return;
            if (cancelled) { snapBack(0); return; }
            const v = sfVelocity(s, e.timeStamp);
            const h = sheet.offsetHeight;
            if (v >= 0 && y + sfProject(v) > Math.min(h / 2, 240)) dismiss(v);
            else snapBack(v);
        }
        overlay.addEventListener('touchend', function (e) { release(e, false); }, { passive: true });
        overlay.addEventListener('touchcancel', function (e) { release(e, true); }, { passive: true });
    })();

    // החלפת סוג שומרת את הפרויקט שנבחר, אם הוא עוקב גם אחרי הסוג החדש
    // (‎buildProjectSelect‎ מוריד אותו אם לא). קודם כל החלפה איפסה אותו.
    toggleExp.addEventListener('click', () => setType('expense', undefined, undefined, txProject.value));
    toggleInc.addEventListener('click', () => setType('income', undefined, undefined, txProject.value));
    toggleSav.addEventListener('click', () => setType('savings', undefined, undefined, txProject.value));

    // Owner toggle
    ownerToggle.addEventListener('click', function (e) {
        const btn = e.target.closest('.owner-btn');
        if (!btn) return;
        ownerToggle.querySelectorAll('.owner-btn').forEach(function (b) {
            b.classList.remove('active');
            b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');
        txOwner.value = btn.dataset.value;
    });

    // Category grid
    categoryGrid.addEventListener('click', function (e) {
        const btn = e.target.closest('.cat-btn');
        if (!btn) return;
        categoryGrid.querySelectorAll('.cat-btn').forEach(function (b) {
            b.classList.remove('active');
            b.setAttribute('aria-checked', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-checked', 'true');
        if (categoryGridIsProject) {
            txProjectCategory.value = btn.dataset.value;
            txCategory.value = '';
        } else {
            txCategory.value = btn.dataset.value;
            txProjectCategory.value = '';
        }
    });

    // שינוי בחירת הפרויקט מרענן את מקור הקטגוריות (קטגוריות הפרויקט או המשפחה)
    // השדה בתחתית הטופס, והקטגוריות מעליו מתחלפות לקטגוריות הפרויקט — אז
    // לוקחים את המשתמש אליהן, במקום להשאיר אותו עם קטגוריה של הבית שכבר
    // לא מסומנת ורשת חדשה שהוא לא רואה
    txProject.addEventListener('change', function () {
        refreshCategoryGrid();
        const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        categoryLabel.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' });
        categoryGrid.classList.remove('flash');
        void categoryGrid.offsetWidth;
        categoryGrid.classList.add('flash');
    });

    // Recurring
    recurringCb.addEventListener('change', function () {
        recurFields.classList.toggle('visible', this.checked);
    });

    // ── סריקת קבלה: לחיצה פותחת מצלמה/בחירת קובץ ──
    scanBtn.addEventListener('click', function () {
        receiptInput.click();
    });

    // דוחסים בצד הלקוח לפני ההעלאה — קובץ קטן יותר, זול יותר, מהיר יותר.
    // WebP באיכות 80% נותן קובץ הרבה יותר קטן מ-JPEG; דפדפנים ישנים
    // שאינם תומכים ב-toBlob('image/webp') מחזירים blob ריק — נופלים
    // אז חזרה ל-JPEG באותה איכות.
    function compressImage(file) {
        return new Promise(function (resolve) {
            const img = new Image();
            const reader = new FileReader();
            reader.onload = function () { img.src = reader.result; };
            img.onload = function () {
                const MAX = 1200;
                let w = img.width, h = img.height;
                if (w > MAX || h > MAX) {
                    const scale = MAX / Math.max(w, h);
                    w = Math.round(w * scale);
                    h = Math.round(h * scale);
                }
                const canvas = document.createElement('canvas');
                canvas.width = w;
                canvas.height = h;
                canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                canvas.toBlob(function (webpBlob) {
                    if (webpBlob && webpBlob.size > 0) {
                        resolve({ blob: webpBlob, ext: 'webp' });
                    } else {
                        canvas.toBlob(function (jpegBlob) {
                            resolve({ blob: jpegBlob || file, ext: 'jpg' });
                        }, 'image/jpeg', 0.8);
                    }
                }, 'image/webp', 0.8);
            };
            img.onerror = function () { resolve({ blob: file, ext: 'jpg' }); };
            reader.readAsDataURL(file);
        });
    }

    receiptInput.addEventListener('change', function () {
        const file = this.files[0];
        if (!file) return;

        // מציגים תצוגה מקדימה מיידית ו"מפענח נתונים…" בשדות — בלי לחסום
        // את הטופס: המשתמש יכול להמשיך להקליד ידנית תוך כדי שהשרת עובד
        scannerThumbnail.src = URL.createObjectURL(file);
        scanWrapper.classList.add('active');
        scanBtn.disabled = true;
        scanBtn.querySelector('.scan-btn-text').textContent = 'סורק…';
        txAmount.placeholder = 'מפענח נתונים…';
        txDescription.placeholder = 'מפענח נתונים…';
        formError.textContent = '';

        const mySeq = ++scanSeq;
        compressImage(file).then(function (result) {
            const formData = new FormData();
            formData.append('image', result.blob, 'receipt.' + result.ext);
            return fetch('/api/receipts/scan', { method: 'POST', body: formData });
        })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
            // הטופס נסגר או הוחלף בזמן הפענוח: לא נוגעים בו — גם לא ב-UI של
            // הסריקה שלו — והתמונה שהועלתה נמחקת.
            if (mySeq !== scanSeq) {
                if (result.ok && result.data) discardReceipt(result.data.receipt_path);
                return;
            }
            // סריקה שנייה באותו טופס: הקבלה הקודמת כבר לא תישמר
            const previous = txReceiptPath.value;
            resetScanUI();
            if (!result.ok || result.data.error) {
                formError.textContent = (result.data && result.data.error) || 'לא הצלחנו לקרוא את הקבלה — נסו שוב או הזינו ידנית';
                return;
            }
            const data = result.data;
            txAmount.value = data.amount;
            if (data.merchant) txDescription.value = data.merchant;
            if (data.date) txDate.value = data.date;
            if (previous && previous !== data.receipt_path) discardReceipt(previous);
            txReceiptPath.value = data.receipt_path || '';
            if (data.category_id) {
                const catBtn = categoryGrid.querySelector(`[data-value="${data.category_id}"]`);
                if (catBtn) {
                    categoryGrid.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
                    catBtn.classList.add('active');
                    txCategory.value = catBtn.dataset.value;
                }
            }
            scanBtn.querySelector('.scan-btn-text').textContent = '✓ סריקה הושלמה';
            window.showToast('הנתונים פוענחו, נא לוודא לפני שמירה');
        })
        .catch(function () {
            if (mySeq !== scanSeq) return;
            resetScanUI();
            formError.textContent = window.sfNetError() + '. אפשר גם להזין ידנית.';
        });
    });

    // Submit → POST (add) or PUT (edit)
    // בונה שורת "עסקה אחרונה" זמנית לדף הבית — לפני שהשרת בכלל ענה. משפרת
    // תחושת מהירות בהוספה בלבד (לא בעריכה): הפרטים המדויקים (שיוך צבעוני
    // וכו') יגיעו עם הרענון המלא שקורה בהצלחה בכל מקרה, אז לא מדובר בעדכון
    // state אמיתי — רק תצוגה מקדימה חלקית ומהירה.
    function buildPlaceholderTxRow(amount) {
        const li = document.createElement('li');
        // בלי data-id: משאיר את השורה הזמנית לא-אינטרקטיבית (לא ניתנת
        // ללחיצה/swipe) כל עוד היא לא הפכה לעסקה אמיתית עם id מהשרת —
        // מונע ניסיון עריכה/מחיקה על "pending" שלא קיים ב-DB
        li.className = 'transaction-item tx-pending';

        const activeCatBtn = categoryGrid.querySelector('.cat-btn.active');
        const icon = activeCatBtn ? (activeCatBtn.querySelector('.cat-emoji') || {}).textContent : '';
        const nameSpan = activeCatBtn ? activeCatBtn.querySelectorAll('span')[1] : null;
        const name = nameSpan ? nameSpan.textContent : 'אחר';

        const sign = currentType === 'expense' ? '-' : (currentType === 'income' ? '+' : '');
        const desc = txDescription.value.trim();

        li.innerHTML =
            '<div class="tx-head">' +
                '<div class="tx-icon ' + currentType + '"><span class="tx-emoji">' + escapeHtml(icon || '📦') + '</span></div>' +
                '<div class="tx-details">' +
                    '<p class="tx-name"></p>' +
                    '<p class="tx-meta"></p>' +
                '</div>' +
                '<div class="tx-side"><p class="tx-amount ' + currentType + '"></p></div>' +
            '</div>';
        li.querySelector('.tx-name').textContent = name;
        // היום בתוך השורה, כמו בשורות מהשרת (מתן, 30.9)
        const day = txDate.value === todayStr() ? 'היום'
                  : txDate.value === dateStr(-1) ? 'אתמול'
                  : (txDate.value || '').slice(8, 10).replace(/^0/, '') + '.' + (txDate.value || '').slice(5, 7).replace(/^0/, '');
        li.querySelector('.tx-meta').textContent = day + (desc ? ' · ' + desc : '');
        li.querySelector('.tx-amount').textContent = sign + '₪' + window.sfMoney(amount);
        return li;
    }

    // ניקוי סימון-שגיאה של שדה הסכום ברגע שמתקנים אותו (נגישות)
    txAmount.addEventListener('input', function () {
        txAmount.removeAttribute('aria-invalid');
    });

    // כפתור השמירה הוא <label>, לא <button> — ראה ההערה ליד הסימון.
    // המחיר: אין disabled אמיתי, אז חוסמים לחיצה כפולה בדגל, ואת
    // הכיבוי החזותי עושים במחלקה.
    let isSubmitting = false;

    function setSubmitBusy(busy) {
        isSubmitting = busy;
        submitBtn.classList.toggle('is-busy', busy);
        submitBtn.setAttribute('aria-disabled', busy ? 'true' : 'false');
    }

    // ── "בטל" אחרי עריכה (מתן, 30.9 — סבב 6, פריט 10) ──
    // הביטול הוא עריכה נוספת עם הערכים הקודמים, ועם ‎if_match‎ — מה שהעריכה
    // שלנו השאירה. אם מישהו שינה את העסקה מאז, השרת מחזיר 409 ולא דורס.
    // נשמר ב-sessionStorage כי רוב העמודים מתרעננים ברענון מלא אחרי עריכה.
    const UNDO_KEY = 'sf_undo_edit';
    function undoSpec(before, after, message) {
        return {
            id: before.id,
            message: message,
            body: {
                amount: parseFloat(before.amount), type: before.type,
                category_id: before.projectId ? null : (before.categoryId || null),
                project_category_id: before.projectId ? (before.projectCategoryId || null) : null,
                description: before.description || '', date: before.date,
                owner: before.userId || 'shared',
                is_recurring: !!before.isRecurring,
                recurring_frequency: before.isRecurring ? (before.recurringFrequency || null) : null,
                recurring_end_date: before.isRecurring ? (before.recurringEndDate || null) : null,
                project_id: before.projectId || null,
            },
            if_match: {
                amount: after.amount, type: after.type, date: after.date,
                description: after.description || '', category_id: after.category_id || null,
                project_category_id: after.project_category_id || null, user_id: after.user_id || null,
            },
        };
    }
    function rememberUndo(spec) {
        try { sessionStorage.setItem(UNDO_KEY, JSON.stringify(spec)); }
        catch (e) { window.sfToastAfterReload(spec.message); }
    }
    function runUndo(spec) {
        fetch('/api/transactions/' + spec.id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(Object.assign({}, spec.body, { if_match: spec.if_match })),
        })
            .then(function (r) { return r.json().catch(function () { return {}; }); })
            .then(function (d) {
                if (d.error) { window.showToast(d.error, 'error'); return; }
                if (document.querySelector('main[data-soft-reload]')) {
                    window.softReload(null, 'השינוי בוטל').then(function (how) {
                        if (how !== 'reloaded') window.showToast('השינוי בוטל');
                    });
                } else {
                    window.sfToastAfterReload('השינוי בוטל');
                    window.location.reload();
                }
            })
            .catch(function () { window.showToast(window.sfNetError(), 'error'); });
    }
    function showPendingUndo() {
        let spec = null;
        try {
            spec = JSON.parse(sessionStorage.getItem(UNDO_KEY) || 'null');
            sessionStorage.removeItem(UNDO_KEY);
        } catch (e) { return; }
        if (!spec || !spec.id) return;
        window.showToast(spec.message, undefined, { label: 'ביטול', onClick: function () { runUndo(spec); } });
    }
    showPendingUndo();          // אחרי רענון מלא — ההודעה עם "בטל" מחכה כאן

    function requestSubmit() {
        if (typeof txForm.requestSubmit === 'function') txForm.requestSubmit();
        else txForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }

    // מגע בכפתור מחליף את המתג (וזה מה שמפיק את הנקישה ב-iOS) — ומכאן
    // ממשיכים לשליחה הרגילה. השליחה תלויה בשינוי המתג ולא בלחיצה עצמה,
    // כי על תווית אין אירוע "לחיצה" שאפשר לסמוך עליו בכל הדפדפנים.
    const hapticSubmit = document.getElementById('hapticSubmit');
    if (hapticSubmit) {
        hapticSubmit.addEventListener('change', function () { requestSubmit(); });
    }

    // מקלדת: תווית עם role="button" לא נשלחת מעצמה ב-Enter/רווח
    submitBtn.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        requestSubmit();
    });

    // ── לפני שמירה של עסקה חדשה: כפילות? סכום חריג? (מתן, 30.9 — סבב 6, 6–7) ──
    // שאלות ולא חסימות. תקלה ברשת כאן לא עוצרת שמירה — עדיף לשמור בלי
    // אזהרה. אחרי אישור השליחה רצה שוב, ו-‎precheckPassed‎ מדלג על הבדיקה
    // לאותם נתונים בדיוק.
    let precheckPassed = null;
    function precheckKey(p) {
        return [formSeq, p.amount, p.type, p.category_id, p.project_category_id, p.date].join('|');
    }
    function chosenCategoryName() {
        const btn = categoryGrid.querySelector('.cat-btn.active');
        const span = btn ? btn.querySelectorAll('span')[1] : null;
        return span ? span.textContent : 'הקטגוריה';
    }
    function dayWord(iso) {
        if (iso === dateStr(0)) return 'היום';
        if (iso === dateStr(-1)) return 'אתמול';
        return iso.slice(8, 10) + '.' + iso.slice(5, 7);
    }
    function runPrecheck(payload) {
        return fetch('/api/transactions/precheck', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .catch(function () { return {}; })
            .then(function (res) {
                const name = chosenCategoryName();
                let chain = Promise.resolve(true);
                const d = res && res.duplicate;
                if (d) {
                    chain = chain.then(function () {
                        return window.appConfirm({
                            title: 'נראה שהעסקה הזאת כבר קיימת',
                            message: name + ' · ₪' + window.sfMoney(d.amount) + ' · ' + dayWord(d.date)
                                + (d.description ? ' · ' + d.description : '')
                                + (d.by ? '\nהוזנה ע״י ' + d.by + (d.time ? ' ב-' + d.time : '') : ''),
                            confirmText: 'להוסיף בכל זאת',
                            cancelText: 'ביטול',
                            danger: false,
                        }).then(function (ok) { return !!ok; });
                    });
                }
                const u = res && res.unusual;
                if (u) {
                    chain = chain.then(function (ok) {
                        if (!ok) return false;
                        return window.appConfirm({
                            title: '₪' + window.sfMoney(payload.amount) + ' על ' + name + '?',
                            message: 'בדרך כלל אתם ' + (payload.type === 'savings' ? 'מפרישים' : 'מוציאים')
                                + ' שם בין ₪' + window.sfMoney(u.min) + ' ל-₪' + window.sfMoney(u.max),
                            confirmText: 'כן, זה נכון',
                            cancelText: 'לתקן',
                            danger: false,
                        }).then(function (ok2) {
                            if (!ok2) { txAmount.focus(); txAmount.select(); }
                            return !!ok2;
                        });
                    });
                }
                return chain;
            });
    }

    txForm.addEventListener('submit', function (e) {
        e.preventDefault();
        if (isSubmitting) return;
        formError.textContent = '';
        txAmount.removeAttribute('aria-invalid');

        const amount = parseFloat(txAmount.value);
        if (!amount || amount <= 0 || !isFinite(amount)) {
            formError.textContent = 'נא להזין סכום תקין';
            txAmount.setAttribute('aria-invalid', 'true');
            txAmount.setAttribute('aria-describedby', 'formError');
            txAmount.focus();
            return;
        }

        // השרת דוחה בלי קטגוריה בכל מקרה; כאן רק אומרים את זה לפני הבקשה
        if (!(txProject.value ? txProjectCategory.value : txCategory.value)) {
            formError.textContent = 'נא לבחור קטגוריה';
            return;
        }

        const payload = {
            amount:              amount,
            type:                currentType,
            category_id:         txCategory.value || null,
            project_category_id: txProjectCategory.value || null,
            description:         txDescription.value.trim(),
            date:                txDate.value,
            owner:               window.SF_ATTRIBUTION[currentType] ? (txOwner.value || null) : null,
            is_recurring:        recurringCb.checked,
            recurring_frequency: recurringCb.checked ? txFrequency.value : null,
            recurring_end_date:  recurringCb.checked ? (txEndDate.value || null) : null,
            receipt_path:        currentType === 'expense' ? (txReceiptPath.value || null) : null,
            project_id:          txProject.value || null,
        };

        if (!editId && precheckPassed !== precheckKey(payload)) {
            const key = precheckKey(payload);
            const mySeq = formSeq;
            setSubmitBusy(true);
            submitLabel.textContent = 'בודק…';
            runPrecheck(payload).then(function (ok) {
                if (mySeq !== formSeq) return;          // הטופס התחלף בינתיים
                setSubmitBusy(false);
                updateSubmitLabel();
                // הטופס נסגר בזמן "בודק…" — המשתמש ויתר. בלי זה העסקה נשמרה בכל
                // זאת, ועם קבלה שהסגירה כבר מחקה.
                if (!overlay.classList.contains('open')) return;
                if (!ok) return;
                precheckPassed = key;
                requestSubmit();
            });
            return;
        }
        precheckPassed = null;

        setSubmitBusy(true);
        submitLabel.textContent = 'שומר…';
        // מעכשיו הקבלה שייכת לשמירה הזאת — ראו ‎claimedReceipt‎. כל כשל למטה
        // משחרר אותה, כדי שסגירה בלי ניסיון נוסף כן תמחק אותה.
        claimedReceipt = payload.receipt_path;

        // מה ששייך לשמירה **הזאת**, ולא למה שפתוח כשהתשובה חוזרת
        const myForm   = formSeq;
        const myEditId = editId;
        const myOriginal = editId ? editingOriginal : null;
        const mySeries = !!(editId && editingSeries);
        const myLabel  = '₪' + amount + (payload.description ? ' (' + payload.description + ')' : '');
        // האם הטופס של השמירה הזאת כבר לא על המסך — כי נפתח טופס אחר מאז
        function formWasReplaced() { return formSeq !== myForm; }

        // UI אופטימי: רק בהוספה חדשה (לא עריכה) ורק בדף הבית — שם יש רשימת
        // "עסקאות אחרונות" מוכרת שאפשר להוסיף לה שורה זמנית מיד, לפני
        // שהשרת בכלל ענה. שאר הדף (כרטיסי סיכום, גרפים) ממשיך להתעדכן
        // רק ברענון המלא שקורה בהצלחה ממילא.
        // עסקה שמשויכת לפרויקט לא מוצגת בדף הבית כלל, אז אין לה שורה
        // זמנית — אחרת הייתה מהבהבת לרגע ונעלמת ברענון
        let placeholderRow = null;
        if (!editId && !txProject.value && window.location.pathname === '/') {
            const list = document.querySelector('.transactions-list');
            // ‎closeModal‎ חייב להיות **בתוך** התנאי. בדשבורד ריק אין
            // רשימה בכלל (התבנית מרנדרת אותה רק כשיש עסקאות), אז לא
            // נוצרה שורה זמנית — אבל החלון נסגר בכל זאת, וכל הודעת
            // שגיאה נכתבה לתוך חלון סגור שזה עתה נוקה. העסקה הראשונה
            // בחיים של המשתמש נכשלה בלי שום סימן על המסך.
            if (list) {
                placeholderRow = buildPlaceholderTxRow(amount);
                // בראש הרשימה — הרשימה בסדר ההזנה, החדשה למעלה
                list.insertBefore(placeholderRow, list.firstChild);
                closeModal();
                setSubmitBusy(false);
                updateSubmitLabel();
            }
        }

        // הסגירה האופטימית ניקתה את שדה הקבלה (‎closeModal‎ → ‎resetScanUI‎), אז
        // בפתיחה מחדש אחרי כשל היא חוזרת — אחרת הניסיון הבא נשמר בלעדיה.
        function reopenAfterFailure() {
            openModal();
            txReceiptPath.value = payload.receipt_path || '';
        }

        // השמירה נכשלה אחרי שכבר פתחו טופס חדש: לא פותחים עליו את הישן ולא
        // כותבים לתוכו שגיאה — אומרים איזו עסקה לא נשמרה, כדי שאפשר יהיה
        // להקליד אותה שוב. הקבלה שלה כבר לא תישמר.
        function failedBehindAnotherForm(reason) {
            claimedReceipt = null;
            discardReceipt(payload.receipt_path);
            window.showToast('העסקה של ' + myLabel + ' לא נשמרה — ' + reason, 'error');
        }

        const url    = editId ? ('/api/transactions/' + editId) : '/api/transactions';
        const method = editId ? 'PUT' : 'POST';

        function send(confirmed) {
            const query = [mySeries ? 'from_now=1' : '', confirmed ? 'confirm=1' : ''].filter(Boolean).join('&');
            return fetch(url + (query ? '?' + query : ''), {
                method:  method,
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload),
            }).then(function (r) {
                // תשובה שאינה JSON — דף שגיאה של השרת או של Railway (502/504,
                // פריסה באמצע) — הפכה ל"שגיאת רשת — נסה שוב". אבל הבקשה כבר
                // הגיעה לשרת, וייתכן שהשמירה נכתבה לפני שהוא נפל: "נסה שוב"
                // יצר עותק. אז אומרים את מה שידוע באמת.
                return r.json().then(
                    function (d) { return { code: r.status, d: d }; },
                    function () {
                        return { code: r.status, d: { error: myEditId
                            ? 'השרת לא ענה כמו שצריך — ייתכן שהשינוי כבר נשמר. רעננו ובדקו לפני שמנסים שוב.'
                            : 'השרת לא ענה כמו שצריך — ייתכן שהעסקה כבר נשמרה. בדקו ברשימה לפני שמנסים שוב.' } };
                    });
            });
        }

        send(false)
        .then(function (res) {
            // סדרה קבועה שתייצר עשרות שורות אחורה — כמעט תמיד טעות
            // הקלדה בתאריך. השרת עונה 409 עם המספר האמיתי, ושואלים.
            if (res.code === 409 && res.d.needs_confirm) {
                if (placeholderRow && formWasReplaced()) {
                    placeholderRow.remove(); placeholderRow = null;
                    failedBehindAnotherForm(res.d.error);
                    return null;
                }
                if (placeholderRow) { placeholderRow.remove(); placeholderRow = null; reopenAfterFailure(); }
                return window.appConfirm({
                    title: 'ליצור ' + res.d.will_create + ' עסקאות אחורה?',
                    message: res.d.error,
                    confirmText: 'כן, ליצור',
                }).then(function (ok) {
                    if (!ok) {
                        claimedReceipt = null;
                        setSubmitBusy(false);
                        updateSubmitLabel();
                        return null;
                    }
                    return send(true);
                });
            }
            return res;
        })
        .then(function (res) {
            if (!res) return;                       // המשתמש ביטל
            const data = res.d;
            if (data.error && placeholderRow && formWasReplaced()) {
                placeholderRow.remove();
                placeholderRow = null;
                failedBehindAnotherForm(data.error);
                return;
            }
            if (data.error) {
                // בכשל **שרת** החלון נשאר סגור, והשדות — שעדיין מלאים,
                // כי ‎closeModal‎ לא מאפס אותם — הפכו לבלתי נגישים: הדרך
                // היחידה חזרה היא ה-FAB, ו-‎openAddModal‎ מנקה אותם. הטוסט
                // נעלם אחרי 2.6 שניות, והמשתמש הקליד הכול מחדש ונכשל שוב
                // מאותה סיבה שכבר לא הייתה על המסך. זה אותו תיקון שנעשה
                // לכשל רשת, בענף שפוספס.
                if (placeholderRow) {
                    placeholderRow.remove();
                    placeholderRow = null;
                    reopenAfterFailure();
                }
                formError.textContent = data.error;
                claimedReceipt = null;
                setSubmitBusy(false);
                updateSubmitLabel();
                return;
            }

            // עסקה חדשה נכנסה — צליל ונקישה. חייב לקרות כאן, בתוך שרשרת
            // הלחיצה של המשתמש, כי iOS מאפשר שמע רק מתוך אינטראקציה.
            const isNew = !myEditId;
            if (isNew) window.appFeedback();

            // מה שפעולת-המשך (למטה) רוצה שהמשתמש יידע, במקום ההודעה הרגילה
            let followUp = null;
            // עסקה קבועה שנערכה מההגדרות: מאיזה תאריך השינוי חל. בלי "ביטול" —
            // הסדרה התפצלה, ואין עסקה אחת להחזיר
            // הוצאה חדשה שחצתה את התקציב של הקטגוריה (מתן, 3.10 — רעיון 17)
            if (isNew && data.budget_note) {
                followUp = { text: 'העסקה נוספה. ' + data.budget_note };
            }
            if (data.series_from) {
                const d = data.series_from;
                followUp = { text: 'העסקה הקבועה עודכנה — מ-' + d.slice(8, 10) + '.' + d.slice(5, 7)
                                   + ' והלאה. החודשים הקודמים לא השתנו', series: true };
            }

            function finish() {
                // אם בינתיים נפתח טופס חדש — הוא של המשתמש, לא שלנו
                if (!formWasReplaced()) {
                    // הכפתור נשאר "שומר…" אחרי הצלחה. בעמוד שמתרענן ברענון
                    // רך (הבית) ה-JS לא נטען מחדש, אז העריכה הבאה נתקלה
                    // בכפתור תקוע: הלחיצה לא עשתה כלום ובלי שום הודעה. מתן:
                    // "לפעמים זה לא נותן לי ללחוץ על שמירת שינויים".
                    setSubmitBusy(false);
                    updateSubmitLabel();
                    closeModal();
                }
                // רענון רך: מחליף את תוכן העמוד בלי ניווט, בלי ניתוח מחדש
                // של ה-CSS וה-JS, ובלי לאבד את מיקום הגלילה. ההשהיה של
                // 380ms הייתה שם רק כדי שהצליל יסתיים לפני שהדף נעלם —
                // עכשיו הוא לא נעלם, אז היא מיותרת.
                const message = followUp ? followUp.text : (myEditId ? 'העסקה עודכנה' : 'העסקה נוספה');
                // "בטל" אחרי עריכה — לא כשהסדרה שונתה להבא, ולא אחרי כשל
                const undo = (myOriginal && data.transaction && !(followUp && (followUp.series || followUp.error)))
                    ? undoSpec(myOriginal, data.transaction, message) : null;
                if (document.querySelector('main[data-soft-reload]')) {
                    if (undo) rememberUndo(undo);
                    window.softReload(null, undo ? null : message).then(function (how) {
                        if (how === 'reloaded') return;   // תוצג אחרי הטעינה המלאה
                        if (undo) { showPendingUndo(); return; }
                        window.showToast(message, followUp && followUp.error ? 'error' : undefined);
                    });
                } else {
                    // עמוד עם גרפים או האזנות ישירות — רענון מלא, כמו קודם
                    if (undo) rememberUndo(undo);
                    else window.sfToastAfterReload(message);
                    setTimeout(function () { window.location.reload(); }, isNew ? 380 : 0);
                }
            }

            const sideEffects = [];

            // סנכרון חכם: אם עורכים מופע שנוצר מעסקה קבועה ושינו את הסכום —
            // מציעים לעדכן גם את התבנית, כדי שמופעים עתידיים ישתמשו בו
            //
            // "להבא" מפצל את הסדרה במופע הזה (ראו ‎split_recurring_series‎):
            // החודשים הקודמים לא משתנים. שני המזהים נלכדים לפני שאלת האישור
            // ולא נקראים אחריה: פתיחת עסקה אחרת מחליפה אותם, והשאלה מחכה למשתמש.
            if (editingRecurringParentId && amount !== originalAmount) {
                const templateId = editingRecurringParentId;
                const instanceId = editId;
                sideEffects.push(function () {
                    return window.appConfirm({
                        title: 'לעדכן גם את החודשים הבאים?',
                        message: 'שיניתם את הסכום. להמשיך איתו גם בחודשים הבאים? החודשים שכבר עברו יישארו כמו שהם.',
                        confirmText: 'עדכון להבא',
                        danger: false,
                    }).then(function (ok) {
                        if (!ok) return;
                        const failed = function (why) {
                            followUp = { error: true,
                                         text: 'העסקה עודכנה, אבל הסכום לחודשים הבאים לא השתנה — ' + why };
                        };
                        return fetch('/api/recurring/' + templateId + '/sync', {
                            method:  'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body:    JSON.stringify({ instance_id: instanceId }),
                        }).then(function (r) {
                            if (r.ok) {
                                followUp = { text: 'העסקה עודכנה, והסכום החדש ימשיך מהחודש הזה', series: true };
                                return;
                            }
                            return r.json().then(function (d) { failed((d && d.error) || 'נסו שוב'); },
                                                 function () { failed('נסו שוב'); });
                        }, function () {
                            // כאן כשל נבלע עד היום בשקט: המשתמש ענה "עדכן להבא",
                            // שמע "העסקה עודכנה", והחודש הבא נוצר בסכום הישן.
                            failed(window.sfNetError());
                        });
                    });
                });
            }

            sideEffects
                .reduce(function (chain, fn) { return chain.then(fn); }, Promise.resolve())
                .then(finish);
        })
        .catch(function () {
            if (placeholderRow && formWasReplaced()) {
                placeholderRow.remove();
                failedBehindAnotherForm(window.sfNetError());
                return;
            }
            if (placeholderRow) {
                placeholderRow.remove();
                // החלון כבר נסגר אופטימית, אבל מה שהוקלד עדיין בשדות —
                // ‎closeModal‎ לא מאפס אותם. פותחים אותו בחזרה במקום
                // להשאיר את המשתמש עם הודעת שגיאה וטופס ריק: במוסך או
                // בחניון, "נסה שוב" פירושו היה להקליד הכול מחדש, בלי
                // רשת, בדיוק כשהוא הכי לא רוצה.
                reopenAfterFailure();
            }
            formError.textContent = window.sfNetError();
            claimedReceipt = null;
            setSubmitBusy(false);
            updateSubmitLabel();
        });
    });

    // מוחק עסקה בפועל (אחרי אישור) — משמש גם את כפתור המחיקה במודאל וגם
    // את פעולת ה-swipe על שורת עסקה, כדי לא לשכפל את אותה לוגיקה
    // מחיקה עם אפשרות ביטול: מוחקים מיד בשרת ומסירים את השורה מה-DOM (בלי
    // reload מיידי שמכווץ רשימות פתוחות), ומציגים טוסט "בטל" ל-6 שניות.
    // ב"בטל" משחזרים ע"י re-POST מנתוני השורה (קבלה מצורפת, אם הייתה, לא
    // משוחזרת). אם לא ביטלו — reload בתום החלון כדי לרענן סיכומים (יתרה/KPI).
    let pendingDeleteReload = null;

    /* הרענון בתום חלון הביטול קיים כדי לעדכן את הסיכומים (יתרה, KPI)
     * אחרי שהשורה הוסרה. אבל הוא היה ‎location.reload()‎ שרץ בכפייה —
     * ואם בינתיים המשתמש פתח את המודאל והתחיל להקליד, הדף נטען מחדש
     * באמצע מילה והכול אבד. זה בדיוק הרצף שאדם עושה: מוחק עסקה שגויה,
     * ומיד מקליד את התיקון.
     *
     * אז: כשמשהו פתוח לעריכה — דוחים. וכשאפשר, משתמשים ברענון הרך,
     * שממילא לא נוגע במודאל (הוא יושב מחוץ ל-main). */
    let refreshWhenEditingEnds = false;

    function somethingIsBeingEdited() {
        return overlay.classList.contains('open');
    }

    function refreshAfterDelete() {
        if (somethingIsBeingEdited()) {
            refreshWhenEditingEnds = true;
            return;
        }
        refreshWhenEditingEnds = false;
        if (document.querySelector('main[data-soft-reload]')) {
            window.softReload();
        } else {
            window.location.reload();
        }
    }

    // נקרא כשהמודאל נסגר, כדי להשלים רענון שנדחה
    function refreshIfPending() {
        if (refreshWhenEditingEnds && !somethingIsBeingEdited()) refreshAfterDelete();
    }

    /* ── מחיקת עסקה ששייכת לסדרה קבועה ──
     *
     * בדיוק השאלה של יומן: "רק את זו" או "את זו וכל הבאות". אין כאן
     * הבחנה בין "תבנית" למופע — היא פנימית לגמרי, ולמי שמוחק את שכר
     * הדירה של מרץ לא אמור להיות אכפת אם מרץ הוא במקרה החודש שבו
     * הסדרה נפתחה.
     *
     * הבטוחה היא כפתור האישור; ההרסנית עוברת אישור שני עם המספר.
     * נסיגה (Escape או לחיצה בחוץ) מחזירה ‎null‎ ומבטלת — בשני השלבים.
     */
    /* כל השורות של עסקה בעמוד, לא רק זו שממנה המחיקה התחילה. בעמוד החודש
     * אותה עסקה מופיעה ב"כל העסקאות", בקטגוריה שלה ובחלוקה לפי בן משפחה —
     * והעותקים האחרים נשארו לחיצים עד הרענון, על עסקה שכבר לא קיימת. */
    function removeTransactionRows(id, row) {
        if (row) row.remove();
        if (!id) return;
        document.querySelectorAll('.transaction-item, .cat-tx-row, .recurring-row')
            .forEach(function (el) { if (el.dataset.id === id) el.remove(); });
    }

    function askAboutSeries(txData, row, later, onFail) {
        return window.appConfirm({
            title:       'זו עסקה קבועה',
            message:     'אפשר למחוק רק את המופע הזה, או אותו וכל הבאים '
                         + 'אחריו (' + later + ' בסך הכל).',
            confirmText: 'רק את זו',
            cancelText:  'את זו וכל הבאות',
            danger:      false,
        }).then(function (onlyThis) {
            if (onlyThis === null) return;                 // נסיגה
            if (onlyThis) return sendSeriesDelete(txData, row, 'one', 1, onFail);

            return window.appConfirm({
                title:       'למחוק את זו וכל הבאות?',
                message:     window.sfCount(later, 'עסקה אחת תימחק', 'עסקאות יימחקו') + ', והעסקה הקבועה תיעצר כאן. '
                             + 'מה שנרשם בחודשים קודמים יישאר.',
                confirmText: 'מחיקת ' + later,
            }).then(function (sure) {
                if (sure !== true) return;
                return sendSeriesDelete(txData, row, 'later', later, onFail);
            });
        });
    }

    /* בן משפחה אחר מחק את העסקה רגע קודם. זו לא תקלה — מה שהמשתמש ביקש
     * כבר קרה. בלי זה הוא ראה "מחיקה נכשלה", השורה נשארה, וכל ניסיון
     * נוסף נכשל שוב. */
    function alreadyGone(txData, row) {
        removeTransactionRows(txData.id, row);
        window.showToast('העסקה כבר נמחקה');
        clearTimeout(pendingDeleteReload);
        pendingDeleteReload = setTimeout(refreshAfterDelete, 2500);
    }

    function sendSeriesDelete(txData, row, mode, total, onFail) {
        return fetch('/api/transactions/' + txData.id + '?mode=' + mode, { method: 'DELETE' })
            .then(r => r.json().then(d => (r.status === 404 ? null : d)))
            .then(function (d) {
                if (d === null) return alreadyGone(txData, row);
                if (d.status !== 'ok') { if (onFail) onFail(d.error || 'המחיקה נכשלה'); return; }
                removeTransactionRows(txData.id, row);
                // אין כאן "בטל": שחזור של מופע בודד היה מחזיר גם את
                // הדילוג שנרשם עליו, ושל סדרה שלמה — עשרות שורות.
                const n = d.deleted || total;
                window.showToast(mode === 'one'
                    ? 'העסקה נמחקה. שאר החודשים של העסקה הקבועה נשארו'
                    : window.sfCount(n, 'עסקה אחת נמחקה', 'עסקאות נמחקו') + ', והעסקה הקבועה נעצרה');
                clearTimeout(pendingDeleteReload);
                pendingDeleteReload = setTimeout(refreshAfterDelete, 2500);
            })
            .catch(function () { if (onFail) onFail(window.sfNetError()); });
    }

    /* האישור שלפני המחיקה.
     *
     * לעסקה רגילה — השאלה הרגילה. לעסקה ששייכת לסדרה קבועה — **בלי
     * שאלה כאן בכלל**, כי השרת עונה 409 ומיד אחריו נשאלת השאלה
     * האמיתית ("רק את זו / את זו וכל הבאות").
     *
     * קודם שתי השאלות הופיעו בזו אחר זו, והראשונה אמרה "הפעולה תסיר
     * את העסקה מכל הדוחות והגרפים" — משפט שנכון לעסקה בודדת ומטעה
     * לחלוטין כשמאחוריה סדרה שלמה. מתן ראה אותה, וכצפוי הבין שזו
     * השאלה היחידה שתהיה. */
    function confirmDelete(txData) {
        if (txData && (txData.isRecurring || txData.recurringParentId)) {
            return Promise.resolve(true);
        }
        return window.appConfirm({
            title: 'למחוק את העסקה?',
            message: 'הפעולה תסיר את העסקה מכל הדוחות והגרפים.',
            confirmText: 'מחיקת העסקה',
        });
    }

    function deleteWithUndo(txData, row, onFail) {
        // תמונת הקבלה נמחקת מהאחסון יחד עם העסקה, ולכן "בטל" מחזיר את
        // העסקה בלבד — הקובץ כבר לא קיים. זה היה קורה בשקט: המשתמש לחץ
        // "בטל", ראה את העסקה חוזרת, והקבלה פשוט לא הייתה שם יותר.
        // אומרים את זה מראש, ורק כשבאמת הייתה קבלה.
        const hadReceipt = !!(row && row.querySelector('.receipt-badge'));
        fetch('/api/transactions/' + txData.id, { method: 'DELETE' })
            .then(r => r.json().then(d => ({ code: r.status, d: d })))
            .then(function (res) {
                // השרת מזהה שהעסקה שייכת לסדרה קבועה ומסרב למחוק בלי
                // בחירה מפורשת — "רק את זו" או "את זו וכל הבאות".
                if (res.code === 409 && res.d.needs_choice) {
                    return askAboutSeries(txData, row, res.d.later, onFail);
                }
                if (res.code === 404) return alreadyGone(txData, row);
                const d = res.d;
                if (d.status !== 'ok') { if (onFail) onFail(d.error || 'מחיקה נכשלה'); return; }
                removeTransactionRows(txData.id, row);
                window.showToast(hadReceipt
                    ? 'העסקה נמחקה. הקבלה המצורפת נמחקה איתה ולא תחזור'
                    : 'העסקה נמחקה', null, {
                    label: 'ביטול',
                    onClick: function () {
                        clearTimeout(pendingDeleteReload);
                        refreshWhenEditingEnds = false;
                        restoreTransaction(Object.assign({}, txData,
                                                         { hadReceipt: hadReceipt }));
                    },
                });
                clearTimeout(pendingDeleteReload);
                pendingDeleteReload = setTimeout(refreshAfterDelete, 6000);
            })
            .catch(function () {
                if (onFail) onFail(window.sfNetError());
            });
    }

    function restoreTransaction(txData) {
        const payload = {
            amount:              txData.amount,
            type:                txData.type,
            category_id:         txData.categoryId || null,
            project_category_id: txData.projectCategoryId || null,
            description:         txData.description || '',
            date:                txData.date,
            owner:               txData.userId || null,
            is_recurring:        txData.isRecurring,
            recurring_frequency: txData.isRecurring ? txData.recurringFrequency : null,
            recurring_end_date:  txData.isRecurring ? txData.recurringEndDate : null,
            receipt_path:        null,
            project_id:          txData.projectId || null,
        };
        fetch('/api/transactions', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(payload),
        })
        .then(r => r.json())
        .then(function (data) {
            if (data.error) { window.showToast(data.error, 'error'); return; }
            // ‎receipt_path‎ נשלח ‎null‎ במכוון: הקובץ נמחק מהאחסון ברגע
            // המחיקה, וכתובת לקובץ שאינו קיים הייתה מייצרת תג 📎 שבור.
            window.sfToastAfterReload(
                txData.hadReceipt ? 'העסקה שוחזרה — בלי הקבלה' : 'העסקה שוחזרה');
            window.location.reload();
        })
        .catch(function () { window.showToast('שחזור נכשל — נסו שוב', 'error'); });
    }

    // "הוסף שוב" (שכפול): הופך את מודל העריכה הפתוח למודל הוספה חדש עם
    // אותם ערכים ותאריך היום — לרישום מהיר של קנייה חוזרת (קפה, קניות).
    duplicateBtn.addEventListener('click', function () {
        editId = null;
        editingRecurringParentId = null;
        editingSeries = false;
        originalAmount = null;
        modalTitle.textContent = 'הוספת עסקה';
        setEditLook(false);
        editModeActions.style.display = 'none';
        if (enteredMeta) enteredMeta.hidden = true;
        // שכפול הוא עסקה חד-פעמית — לא ממשיכים את מצב ה"קבועה"
        recurringCb.checked = false;
        recurFields.classList.remove('visible');
        txDate.value = todayStr();
        syncDateChips();
        // ‎setType‎ ולא רק ‎updateSubmitLabel‎: כפתור הסריקה מוסתר במצב
        // עריכה (‎!editId && type === 'expense'‎), ושכפול מנקה את ‎editId‎
        // בלי לרענן אותו. השורה המשוכפלת היא הוצאה חדשה לגמרי — ובלי זה
        // היא נפתחה בלי אפשרות לצלם קבלה, בלי שום סיבה נראית לעין.
        setType(currentType);
        updateSubmitLabel();
        txAmount.focus();
        window.showToast('שכפול — עדכנו ושמרו');
    });

    // Delete (edit mode only)
    deleteBtn.addEventListener('click', function () {
        if (!editId) return;
        const row = document.querySelector('[data-id="' + editId + '"]');
        // כשהשורה לא ברשימה (עריכה מהעמוד השני, למשל) — המודאל עצמו
        // כבר יודע אם זו סדרה
        const txData = row ? buildTxFromRow(row)
                           : { id: editId, isRecurring: recurringCb.checked,
                               recurringParentId: editingRecurringParentId };
        confirmDelete(txData).then(function (ok) {
            if (!ok) return;
            closeModal();
            deleteWithUndo(txData, row, function (msg) {
                window.showToast(msg, 'error');
            });
        });
    });

    /* ── תג 📎 על עסקה עם קבלה מצורפת ──
     * אין כאן קוד, וזה התיקון. הגרסה הקודמת שלפה כתובת מהשרת ב-fetch
     * ואז קראה ל-window.open — וב-iOS זה נחסם תמיד: הדפדפן מתיר פתיחת
     * חלון רק כתוצאה ישירה מלחיצה, וההמתנה לשרת מנתקת את הקשר. לא קרה
     * כלום — אין חלון, אין שגיאה, אין רמז — והקבלות שנסרקו פשוט לא היו
     * נגישות מהטלפון.
     *
     * הסמל הוא עכשיו ‎<a href="/receipts/…" target="_blank">‎, והדפדפן
     * מנווט בעצמו. ניווט שנובע מלחיצה לא נחסם.
     *
     * מה שכן חשוב: ‎.receipt-badge‎ מוחרג ממטפלי השורה למטה, אחרת לחיצה
     * עליו הייתה פותחת גם את מודאל העריכה. */

    // דגל שמונע פתיחת עריכה מה"קליק" הסינתטי שהדפדפן יורה אחרי מחוות
    // מגע — בלי זה, swipe שגורר את השורה גם פותח בטעות את מודאל העריכה
    // (touchend שלא קרא ל-preventDefault עדיין מייצר click עוקב)
    let justSwiped = false;

    // בונה את אובייקט ה-tx למודאל העריכה מתוך ה-data attributes של השורה —
    // משמש גם בלחיצה רגילה וגם בפעולת עריכה מ-swipe
    // "87.0" מהשרת מוצג "87"; "87.5" נשאר "87.5" (מתן, 3.10)
    function plainAmount(v) {
        const n = Number(v);
        return isFinite(n) ? String(n) : v;
    }

    // ── השלמה מתיאורים קודמים (מתן, 3.10 — רעיון 41) ──
    // נטען פעם אחת לכל טעינת עמוד; עד 3 הצעות מתחת לשדה, לפי תחילת מילה.
    // לחיצה ממלאת רק את התיאור — הקטגוריה לא נוגעת (מתן ויתר על "זכירת קטגוריה").
    const descSuggest = document.getElementById('descSuggest');
    let pastDescriptions = null;
    function loadDescriptions() {
        if (pastDescriptions || !descSuggest) return;
        pastDescriptions = [];
        fetch('/api/descriptions', { credentials: 'same-origin' })
            .then(r => r.ok ? r.json() : { descriptions: [] })
            .then(d => { pastDescriptions = d.descriptions || []; })
            .catch(() => { pastDescriptions = null; });   // ננסה שוב בפתיחה הבאה
    }
    function hideSuggest() { if (descSuggest) { descSuggest.hidden = true; descSuggest.innerHTML = ''; } }
    function descMatches(q) {
        const needle = q.trim().toLowerCase();
        if (needle.length < 2 || !pastDescriptions) return [];
        return pastDescriptions.filter(function (d) {
            const low = d.toLowerCase();
            if (low === needle) return false;                     // כבר כתוב במלואו
            return low.split(/\s+/).some(w => w.startsWith(needle)) || low.startsWith(needle);
        }).slice(0, 3);
    }
    if (descSuggest) {
        txDescription.addEventListener('input', function () {
            const found = descMatches(txDescription.value);
            descSuggest.innerHTML = '';
            found.forEach(function (text) {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'desc-suggest-item';
                b.setAttribute('role', 'option');
                b.textContent = text;
                descSuggest.appendChild(b);
            });
            descSuggest.hidden = !found.length;
        });
        // ‎mousedown‎ ולא ‎click‎: אחרת ה-blur של השדה מסתיר את ההצעות לפני הלחיצה
        descSuggest.addEventListener('mousedown', function (e) { e.preventDefault(); });
        descSuggest.addEventListener('click', function (e) {
            const b = e.target.closest('.desc-suggest-item');
            if (!b) return;
            txDescription.value = b.textContent;
            hideSuggest();
            txDescription.focus();
        });
        txDescription.addEventListener('blur', function () { setTimeout(hideSuggest, 150); });
    }

    function buildTxFromRow(row) {
        return {
            id:                  row.dataset.id,
            amount:              row.dataset.amount,
            type:                row.dataset.type,
            categoryId:          row.dataset.categoryId,
            projectCategoryId:   row.dataset.projectCategoryId || null,
            description:         row.dataset.description,
            date:                row.dataset.date,
            userId:              row.dataset.userId || '',
            isRecurring:         row.dataset.isRecurring === 'true',
            recurringFrequency:  row.dataset.recurringFrequency,
            recurringEndDate:    row.dataset.recurringEndDate,
            recurringParentId:   row.dataset.recurringParentId || null,
            projectId:           row.dataset.projectId || null,
        };
    }

    // ── פתיחת עריכה בלחיצה על עסקה קיימת (עמוד הבית + עמוד החודש + עסקאות קבועות בהגדרות) ──
    // אותו חלון בכל מקום. בדף הבית הייתה עד 5.10 עריכה בתוך הכרטיסייה —
    // מתן ביקש שתיראה כמו בעמוד החודש.
    document.addEventListener('click', function (e) {
        if (justSwiped) { justSwiped = false; return; }
        if (e.target.closest('.receipt-badge, .delete-recurring-btn, .swipe-action')) return;
        const row = e.target.closest('.transaction-item, .cat-tx-row, .recurring-row');
        if (!row || !row.dataset.id) return;
        openEditModal(buildTxFromRow(row), row);
    });

    // ── אותה פתיחת עריכה במקלדת (Enter/Space) — השורות מסומנות
    // role="button" tabindex="0" בתבניות, בדיוק כמו .legend-item[role=button] הקיים ב-month.html ──
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        if (e.target.closest('.receipt-badge, .delete-recurring-btn, .swipe-action')) return;
        const row = e.target.closest('.transaction-item, .cat-tx-row, .recurring-row');
        if (!row || !row.dataset.id) return;
        e.preventDefault();
        openEditModal(buildTxFromRow(row), row);
    });

    // ── Swipe על שורת עסקה: ימינה חושף "עריכה", שמאלה חושף "מחיקה" ──
    // נוסף על הלחיצה הרגילה, לא מחליף אותה. עובד בכל מקום שיש בו שורת
    // עסקה (דף הבית, עמוד החודש, עסקאות קבועות בהגדרות, עמוד פרויקט).
    (function () {
        const ROW_SELECTOR = '.transaction-item, .cat-tx-row, .recurring-row';
        const OPEN_X = 76;    // מרחק הנעילה הפתוחה, תואם לרוחב .swipe-action
        const THRESHOLD = 42; // לאן התנועה הולכת (מקום + תנופה) — מעבר לזה נפתחת
        const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        let drag = null;
        let anim = null;    // { content, cancel } — הקפיץ שרץ עכשיו, אם יש
        let openRow = null; // השורה שכרגע פתוחה (אם יש), כדי לסגור אותה בלחיצה במקום אחר

        // שורת עסקה קבועה ברשימה של ההגדרות — שם "הסרה" עוצרת את הסדרה
        function isSettingsSeriesRow(row) {
            return row.classList.contains('recurring-row');
        }

        function ensureSwipeStructure(row) {
            if (row.classList.contains('swipe-ready')) return;
            row.classList.add('swipe-ready');

            const content = document.createElement('div');
            content.className = 'swipe-content';
            while (row.firstChild) content.appendChild(row.firstChild);

            const editAction = document.createElement('div');
            editAction.className = 'swipe-action swipe-action-edit';
            editAction.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg> עריכה';

            const deleteAction = document.createElement('div');
            deleteAction.className = 'swipe-action swipe-action-delete';
            // בהגדרות ההחלקה עוצרת את הסדרה (כמו ה-✕ שם), ולא מוחקת — אז
            // היא גם לא נקראת "מחיקה"
            deleteAction.textContent = isSettingsSeriesRow(row) ? '✕ הסרה' : '✕ מחיקה';

            row.appendChild(editAction);
            row.appendChild(deleteAction);
            row.appendChild(content);
        }

        function stopAnim() {
            if (anim) { anim.cancel(); anim = null; }
        }

        // מגיעים ל-‎to‎ בקפיץ שממשיך במהירות של האצבע (‎v‎, px/s). פתיחה
        // אחרי הנפה קופצת טיפה מעבר — הייתה בה תנופה; סגירה נעצרת חלק.
        function settleTo(content, from, to, v) {
            stopAnim();
            if (calm) { content.style.transition = ''; content.style.transform = to ? 'translateX(' + to + 'px)' : ''; return; }
            content.style.transition = 'none';
            const paint = function (x) { content.style.transform = 'translateX(' + x + 'px)'; };
            anim = { content: content, cancel: sfSpring(from, to, v, 0.3, to ? 0.85 : 1, paint, function () {
                anim = null;
                content.style.transition = '';
                if (!to) content.style.transform = '';
            }) };
        }

        function closeRow(row) {
            const content = row.querySelector('.swipe-content');
            if (anim && anim.content === content) stopAnim();
            if (content) { content.style.transition = ''; content.style.transform = ''; }
            row.classList.remove('swipe-open');
            if (openRow === row) openRow = null;
        }

        // המבנה נבנה **בעצלתיים**, ב-‎touchstart‎ בלבד (למטה).
        //
        // קודם הוא נבנה לכל שורה בטעינה: ‎ensureSwipeStructure‎ מעבירה כל
        // ילד ל-div חדש ומוסיפה שני פאנלים, ובעמוד החודש כל עסקה מופיעה
        // פעמיים-שלוש (פירוט לפי קטגוריה, "כל העסקאות", פירוט פרויקט).
        // חודש של 150 עסקאות היה ~350 שורות × reparent + שלוש יצירות
        // אלמנט, סינכרונית, בטעינת העמוד — ובלי שום צורך, כי ה-‎touchstart‎
        // בונה את מה שנוגעים בו ממילא.

        document.addEventListener('touchstart', function (e) {
            if (e.target.closest('.receipt-badge, .delete-recurring-btn, .swipe-action')) return;
            const row = e.target.closest(ROW_SELECTOR);
            if (!row || !row.dataset.id) return;
            ensureSwipeStructure(row);

            if (drag && drag.row !== row) closeRow(drag.row);

            // נגיעה בשורה שכבר פתוחה רק סוגרת אותה (כמו ברוב האפליקציות) —
            // מונע חשבון מסובך של גרירה מתוך מצב פתוח, ומונע גם פתיחת
            // עריכה בטעות מה-click הסינתטי שיגיע אחרי הנגיעה הזו
            if (row.classList.contains('swipe-open')) {
                closeRow(row);
                justSwiped = true;
                setTimeout(function () { justSwiped = false; }, 400);
                drag = null;
                return;
            }

            const touch = e.touches[0];
            drag = {
                row: row,
                content: row.querySelector('.swipe-content'),
                startX: touch.clientX,
                startY: touch.clientY,
                deltaX: 0,
                dragging: false,
                samples: [{ t: e.timeStamp, p: touch.clientX }],
            };
        }, { passive: true });

        document.addEventListener('touchmove', function (e) {
            if (!drag) return;
            const touch = e.touches[0];
            const dx = touch.clientX - drag.startX;
            const dy = touch.clientY - drag.startY;
            if (!drag.dragging) {
                if (Math.abs(dx) < 8) return;
                if (Math.abs(dy) > Math.abs(dx)) { drag = null; return; } // גלילה אנכית — לא swipe
                drag.dragging = true;
                drag.startX += dx > 0 ? 8 : -8;    // בלי קפיצה של 8 הפיקסלים של ההחלטה
                // בלי ההשהיה של ה-CSS: השורה זזה עם האצבע, לא 0.2 שניות אחריה
                if (anim && anim.content === drag.content) stopAnim();
                drag.content.style.transition = 'none';
            }
            // עד רוחב הכפתור — אחד לאחד; מעבר לו — התנגדות שגדלה בהדרגה,
            // במקום קיר ב-100 פיקסלים
            const raw = touch.clientX - drag.startX;
            const over = Math.abs(raw) - OPEN_X;
            drag.deltaX = over <= 0 ? raw : Math.sign(raw) * (OPEN_X + sfRubber(over, drag.row.offsetWidth));
            drag.content.style.transform = 'translateX(' + drag.deltaX + 'px)';
            drag.samples.push({ t: e.timeStamp, p: touch.clientX });
            if (drag.samples.length > 6) drag.samples.shift();
        }, { passive: true });

        document.addEventListener('touchend', function (e) {
            if (!drag) return;
            const { row, content, deltaX, dragging, samples } = drag;
            if (dragging) {
                // מונע פתיחת עריכה מה-click הסינתטי שהדפדפן עשוי לירות אחרי
                // המגע. דפדפנים בדרך כלל לא יורים click אחרי גרירה אמיתית,
                // אז מאפסים את הדגל אחרי רגע כדי לא להשפיע על לחיצות הבאות
                // שלא קשורות לגרירה הזו בכלל.
                justSwiped = true;
                setTimeout(function () { justSwiped = false; }, 400);
            }
            // ההחלטה לפי **לאן התנועה הולכת**: הנפה קצרה ומהירה פותחת, וגרירה
            // ארוכה שחוזרת לאחור — לא. הכיוון — של הנקודה שאליה היא מגיעה.
            const v = dragging ? sfVelocity(samples, e.timeStamp) : 0;
            const aim = deltaX + sfProject(v, 0.99);
            // גרירה לצד אחד והנפה חזרה לצד השני — התחרטות: נסגרת, לא נפתחת הפוך
            if (dragging && Math.abs(aim) > THRESHOLD && (aim > 0) === (deltaX > 0)) {
                const openDir = aim > 0 ? 'right' : 'left';
                content.dataset.openDir = openDir;
                row.classList.add('swipe-open');
                openRow = row;
                settleTo(content, deltaX, openDir === 'right' ? OPEN_X : -OPEN_X, v);
            } else if (dragging) {
                row.classList.remove('swipe-open');
                if (openRow === row) openRow = null;
                settleTo(content, deltaX, 0, v);
            } else {
                closeRow(row);
            }
            drag = null;
        });

        // הדפדפן לקח את המגע (גלילה, חלון מערכת) — השורה חוזרת למקום ולא נתקעת באמצע
        document.addEventListener('touchcancel', function () {
            if (!drag) return;
            if (drag.dragging) closeRow(drag.row);
            drag = null;
        }, { passive: true });

        // לחיצה במקום כלשהו מחוץ לשורה הפתוחה (כולל שורה אחרת) סוגרת אותה
        document.addEventListener('click', function (e) {
            if (openRow && e.target.closest(ROW_SELECTOR) !== openRow) {
                closeRow(openRow);
            }
        });

        // לחיצה על פאנל שנחשף — אותם flows קיימים (עריכה/מחיקה), בלי שכפול קוד
        document.addEventListener('click', function (e) {
            const editBtn = e.target.closest('.swipe-action-edit');
            if (editBtn) {
                const row = editBtn.closest(ROW_SELECTOR);
                closeRow(row);
                openEditModal(buildTxFromRow(row), row);
                return;
            }
            const delBtn = e.target.closest('.swipe-action-delete');
            if (delBtn) {
                const row = delBtn.closest(ROW_SELECTOR);
                // בהגדרות: אותה עצירת סדרה כמו ה-✕ באותה שורה. עד היום ההחלקה
                // הלכה ל-‎DELETE /api/transactions‎ — ומחקה את העסקה הראשונה
                // בסדרה, או את כולה, מתוך שורה שה-✕ שלה מבטיח "כל מה שכבר
                // נרשם יישאר".
                if (isSettingsSeriesRow(row)) {
                    stopSeriesFromSettings(row, function () { closeRow(row); });
                    return;
                }
                const swiped = buildTxFromRow(row);
                confirmDelete(swiped).then(function (ok) {
                    if (!ok) { closeRow(row); return; }
                    deleteWithUndo(swiped, row, function (msg) {
                        closeRow(row);
                        window.showToast(msg, 'error');
                    });
                });
            }
        });
    })();

    /* ── ה-✕ על עסקה קבועה — רק בהגדרות ← עסקאות קבועות ─────────────────
     *
     * "הסרה": עצירת העסקה הקבועה בלי למחוק שום כסף שכבר נרשם. בעמוד החודש
     * היה ✕ נוסף שמחק עסקאות — ומכיוון שהשורה שם הייתה העסקה של החודש
     * הראשון, "רק את זו" מחקה את ינואר. החלק הוסר משם (מתן, 2.10).
     */
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.delete-recurring-btn');
        if (!btn) return;
        const row = btn.closest('.recurring-row');
        if (!row || !row.dataset.id) return;
        stopSeriesFromSettings(row);
    });

    /* עצירת סדרה מתוך "עסקאות קבועות" בהגדרות — ה-✕ וההחלקה שניהם כאן.
     * ‎onCancel‎: מה לעשות אם המשתמש חזר בו (ההחלקה סוגרת את השורה). */
    function stopSeriesFromSettings(row, onCancel) {
        window.appConfirm({
            title: 'להסיר את העסקה הקבועה?',
            message: 'מופעים חדשים יפסיקו להיווצר. כל מה שכבר נרשם — כולל העסקה הראשונה — יישאר בהיסטוריה.',
            confirmText: 'הסרה',
        }).then(function (ok) {
            if (!ok) { if (onCancel) onCancel(); return; }
            // ‎/api/recurring‎ ולא ‎/api/transactions‎: זה עוצר את הסדרה ולא מוחק
            // שורה. שורת התבנית היא העסקה הראשונה בסדרה, ומחיקתה הייתה מוציאה
            // כסף אמיתי מההיסטוריה — בדיוק מה שההודעה למעלה מבטיחה שלא יקרה.
            fetch('/api/recurring/' + row.dataset.id, { method: 'DELETE' })
            .then(r => r.json())
            .then(function (d) {
                if (d.status === 'ok') {
                    row.style.transition = 'opacity 0.25s';
                    row.style.opacity = '0';
                    setTimeout(function () { row.remove(); }, 260);
                    window.showToast('העסקה הקבועה הוסרה');
                } else {
                    window.showToast('ההסרה נכשלה', 'error');
                }
            })
            .catch(function () { window.showToast(window.sfNetError(), 'error'); });
        });
    }

})();
