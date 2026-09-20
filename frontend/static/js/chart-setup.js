/* הגדרות הגרפים — ומה קורה כשהספרייה לא נטענה.
 *
 * אותן שמונה שורות של Chart.defaults הועתקו לשלושה קבצים, ובכל אחד
 * מהם הן ישבו בראש הבלוק שהחזיק גם את כל השאר: פתיחת קטגוריה, חיפוש
 * בעסקאות, מקש Enter/Escape. אם Chart.js לא הגיע — חוסם, רשת גרועה,
 * קובץ פגום במטמון, או פשוט עמוד שלא טוען אותה כי אין מה לצייר —
 * השורה הראשונה זרקה ReferenceError וכל השאר לא רץ מעולם. המשתמש
 * ראה עמוד שנראה תקין לגמרי ופשוט לא הגיב ללחיצות, וזה הבלבול הגרוע
 * ביותר: אין מה לדווח עליו.
 *
 * עכשיו ‎window.sfCharts.ready‎ אומר אם יש ספרייה. קוד הגרפים נכנס
 * מאחורי הדגל, שאר העמוד לא. גרף הוא ממילא קישוט על מספרים שכבר
 * כתובים בעמוד — הוא לא מקור האמת של אף סכום.
 */
window.sfCharts = (function () {
    var COLORS = [
        '#A67C00', '#3D6B54', '#A04545', '#44609B',
        '#75588F', '#3E7373', '#9C6A3C', '#8F5470'
    ];
    var MUTED = '#78716C';
    var GRID  = 'rgba(28,25,23,0.07)';

    // צבעי הגרפים זמינים גם ל-CSS: חלק מהמקראות מרונדרות בשרת, והנקודה
    // לצד כל קטגוריה נצבעת מהמשתנים האלה. לכן זה קורה גם בלי ספרייה —
    // אחרת מקרא שלם היה מאבד את הצבעים שלו על לא עוול בכפו.
    COLORS.forEach(function (c, i) {
        document.documentElement.style.setProperty('--chart-color-' + i, c);
    });

    if (typeof Chart === 'undefined') {
        // במקום קנבס ריק שנראה כמו תקלה — משפט שמסביר, ומבהיר
        // שהמספרים עצמם בסדר.
        document.querySelectorAll('.doughnut-wrap, .line-chart-wrap').forEach(function (wrap) {
            var canvas = wrap.querySelector('canvas');
            if (!canvas) return;
            var note = document.createElement('div');
            note.className = 'chart-empty';
            note.innerHTML =
                '<p>📉</p>' +
                '<p>הגרף לא נטען</p>' +
                '<p>המספרים עצמם מעודכנים ונכונים. רענון העמוד בדרך כלל פותר.</p>';
            canvas.replaceWith(note);
            // המספר שבמרכז הדונאט ממוקם אבסולוטית מעל הקנבס; בלי
            // הקנבס אין לו גובה להתמקם בתוכו, והוא היה נופל על הטקסט
            wrap.classList.add('chart-unavailable');
        });
        return { ready: false, colors: COLORS, muted: MUTED, grid: GRID };
    }

    Chart.defaults.font.family = "'Rubik', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
    Chart.defaults.color = MUTED;
    Chart.defaults.animation.duration = 900;
    Chart.defaults.animation.easing = 'easeOutQuart';
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip.backgroundColor = '#1C1917';
    Chart.defaults.plugins.tooltip.titleColor = '#FAF7F0';
    Chart.defaults.plugins.tooltip.bodyColor = '#E7E0D2';

    return { ready: true, colors: COLORS, muted: MUTED, grid: GRID };
})();
