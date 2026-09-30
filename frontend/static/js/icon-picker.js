/* בחירת אייקון מתוך רשת (מתן, 30.9 — סבב 6, פריט 8).
 *
 * כל ‎.emoji-input‎ באפליקציה: קטגוריות, פרויקטים, קטגוריות של פרויקט,
 * והאשף. נגיעה בשדה פותחת רשת אייקונים לפי נושאים במקום מקלדת — עד היום
 * צריך היה לפתוח את מקלדת האימוג'י, לחפש ולהדביק, ורוב האנשים השאירו 🏷.
 * "אימוג'י אחר" מחזיר את המקלדת לשדה הזה.
 *
 * ובנוסף: כשכותבים שם ("דלק"), השדה שלידו מקבל הצעה (⛽) — כל עוד לא נבחר
 * בו אייקון ביד. השדות מוגבלים לשני תווים (UTF-16), אז ‎U+FE0F‎ רק אחרי תו בודד (‎✈️‎),
 * לא אחרי אימוג'י שכבר תופס שניים (‎🛡‎ ולא ‎🛡️‎). */
(function () {
    const GROUPS = [
        ['אוכל',    ['🛒', '🍽', '☕', '🍕', '🥖', '🍷', '🥗', '🍔']],
        ['בית',     ['🏠', '💡', '💧', '🔥', '🛋', '🧹', '🔨', '🏢']],
        ['רכב',     ['🚗', '⛽', '🔧', '🚌', '🚕', '🚲', '🛵', '🚆']],
        ['ילדים',   ['🧸', '🎒', '🍼', '🏫', '🎈', '👶', '🎨', '📚']],
        ['בריאות',  ['💊', '🏥', '🦷', '👓', '💪', '💆', '🩺', '🧴']],
        ['פנאי',    ['🎬', '🎮', '🏖', '🎉', '🎵', '📺', '🎭', '🐾']],
        ['קניות',   ['🛍', '👕', '👟', '💄', '💇', '🎁', '💍', '📦']],
        ['כסף',     ['💼', '💰', '🏦', '📈', '💳', '🧾', '🏛', '❤️']],
        ['תקשורת',  ['📱', '🌐', '💻', '📡', '📰', '✉️', '🔌', '🛡']],
        ['נסיעות',  ['✈️', '🧳', '🏨', '🗺', '⛺', '🚢', '🌍', '🎫']],
    ];
    // שם ← אייקון. לפי הסדר: הביטוי הראשון שמופיע בשם קובע
    const SUGGEST = [
        ['סופר', '🛒'], ['מכולת', '🛒'], ['קניות לבית', '🛒'], ['מסעד', '🍽'], ['אוכל בחוץ', '🍽'],
        ['קפה', '☕'], ['פיצה', '🍕'], ['דלק', '⛽'], ['רכב', '🚗'], ['טסט', '🚗'], ['מוסך', '🔧'],
        ['חניה', '🚗'], ['תחבורה', '🚌'], ['אוטובוס', '🚌'], ['רכבת', '🚆'], ['מונית', '🚕'],
        ['שכר דירה', '🏠'], ['משכנתא', '🏠'], ['דיור', '🏠'], ['דירה', '🏠'], ['חשמל', '💡'],
        ['מים', '💧'], ['גז', '🔥'], ['ארנונה', '🏛'], ['ועד', '🏢'], ['ניקיון', '🧹'], ['שיפוץ', '🔨'],
        ['רהיט', '🛋'], ['אינטרנט', '🌐'], ['סלולר', '📱'], ['טלפון', '📱'], ['ביטוח', '🛡'],
        ['רופא', '🏥'], ['בריאות', '🏥'], ['קופת חולים', '🏥'], ['תרופ', '💊'], ['מרקחת', '💊'],
        ['שיניים', '🦷'], ['משקפ', '👓'], ['כושר', '💪'], ['ספורט', '💪'], ['גן', '🎒'],
        ['ילד', '🧸'], ['תינוק', '🍼'], ['חיתול', '🍼'], ['בית ספר', '🏫'], ['לימוד', '📚'],
        ['חוג', '🎨'], ['ספר', '📚'], ['בגד', '👕'], ['ביגוד', '👕'], ['נעל', '👟'], ['קניות', '🛍'],
        ['קוסמטיקה', '💄'], ['תספורת', '💇'], ['מספרה', '💇'], ['מתנ', '🎁'], ['חתונה', '💍'],
        ['בילוי', '🎉'], ['סרט', '🎬'], ['קולנוע', '🎬'], ['משחק', '🎮'], ['מנוי', '📺'],
        ['נטפליקס', '📺'], ['טיול', '✈️'], ['חופש', '🏖'], ['טיסה', '✈️'], ['מלון', '🏨'],
        ['כלב', '🐾'], ['חתול', '🐾'], ['חיות', '🐾'], ['משכורת', '💼'], ['שכר', '💼'],
        ['בונוס', '💰'], ['השקע', '📈'], ['מניות', '📈'], ['פנסיה', '🏦'], ['השתלמות', '🏦'],
        ['חיסכון', '🏦'], ['פיקדון', '🏦'], ['תרומ', '❤️'], ['מחשב', '💻'], ['אשראי', '💳'],
    ];
    // ברירות מחדל שאומרות "עוד לא בחרו כלום" — מותר להחליף אותן בהצעה
    const PLACEHOLDERS = ['', '🏷', '🎯', '📦'];

    let sheet = null, target = null;

    function build() {
        sheet = document.createElement('div');
        sheet.className = 'icon-picker';
        sheet.hidden = true;
        sheet.setAttribute('role', 'dialog');
        sheet.setAttribute('aria-modal', 'true');
        sheet.setAttribute('aria-label', 'בחירת אייקון');
        const card = document.createElement('div');
        card.className = 'icon-picker-card';
        const title = document.createElement('p');
        title.className = 'icon-picker-title';
        title.textContent = 'בחירת אייקון';
        card.appendChild(title);
        GROUPS.forEach(function (g) {
            const row = document.createElement('div');
            row.className = 'icon-picker-row';
            const label = document.createElement('span');
            label.className = 'icon-picker-label';
            label.textContent = g[0];
            const grid = document.createElement('div');
            grid.className = 'icon-picker-grid';
            g[1].forEach(function (icon) {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'icon-picker-btn';
                b.textContent = icon;
                b.dataset.icon = icon;
                b.setAttribute('aria-label', g[0] + ' ' + icon);
                grid.appendChild(b);
            });
            row.append(label, grid);
            card.appendChild(row);
        });
        const actions = document.createElement('div');
        actions.className = 'icon-picker-actions';
        const other = document.createElement('button');
        other.type = 'button';
        other.className = 'btn-sm btn-ghost icon-picker-other';
        other.textContent = 'אימוג׳י אחר מהמקלדת';
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'btn-sm btn-ghost icon-picker-cancel';
        cancel.textContent = 'ביטול';
        actions.append(other, cancel);
        card.appendChild(actions);
        sheet.appendChild(card);
        document.body.appendChild(sheet);

        sheet.addEventListener('click', function (e) {
            const pick = e.target.closest('.icon-picker-btn');
            if (pick) { choose(pick.dataset.icon); return; }
            if (e.target.closest('.icon-picker-other')) {
                const input = target;
                close();
                if (input) {
                    input.dataset.freeTyping = '1';
                    input.focus();
                    input.select();
                }
                return;
            }
            if (e.target.closest('.icon-picker-cancel') || e.target === sheet) close();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && sheet && !sheet.hidden) close();
        });
    }

    function open(input) {
        if (!sheet) build();
        target = input;
        sheet.hidden = false;
        const first = sheet.querySelector('.icon-picker-btn');
        if (first) first.focus({ preventScroll: true });
    }
    function close() {
        if (!sheet) return;
        sheet.hidden = true;
        const back = target;
        target = null;
        if (back && !back.dataset.freeTyping) back.focus({ preventScroll: true });
    }
    function choose(icon) {
        if (target) {
            target.value = icon;
            target.dataset.autoIcon = '0';          // נבחר ביד — ההצעה לא דורסת
            target.dispatchEvent(new Event('input', { bubbles: true }));
        }
        close();
    }

    // נגיעה בשדה: הרשת במקום המקלדת. ‎pointerdown‎ עם ‎preventDefault‎ כדי שהמקלדת
    // לא תקפוץ לרגע מתחת לרשת. מי שבחר "אימוג'י אחר" — מקלדת רגילה בשדה הזה.
    document.addEventListener('pointerdown', function (e) {
        const input = e.target.closest && e.target.closest('input.emoji-input');
        if (!input || input.dataset.freeTyping) return;
        e.preventDefault();
        open(input);
    });
    // מקלדת: Enter או רווח בשדה פותחים את הרשת
    document.addEventListener('keydown', function (e) {
        const input = e.target.closest && e.target.closest('input.emoji-input');
        if (!input || input.dataset.freeTyping) return;
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(input); }
    });

    // הצעה לפי השם: שדה טקסט באותה שורה כמו שדה האייקון
    function suggest(name) {
        const n = (name || '').trim();
        if (!n) return null;
        for (let i = 0; i < SUGGEST.length; i++) {
            if (n.indexOf(SUGGEST[i][0]) !== -1) return SUGGEST[i][1];
        }
        return null;
    }
    document.addEventListener('input', function (e) {
        const field = e.target;
        if (!field.matches || !field.matches('input[type="text"]:not(.emoji-input)')) return;
        const row = field.closest('.add-cat-row');
        const icon = row && row.querySelector('input.emoji-input');
        if (!icon || icon.dataset.autoIcon === '0') return;
        if (icon.dataset.autoIcon !== '1' && PLACEHOLDERS.indexOf(icon.value) === -1) return;
        const s = suggest(field.value);
        if (s) { icon.value = s; icon.dataset.autoIcon = '1'; }
    });

    window.sfIconSuggest = suggest;     // לבדיקות
})();
