"""אייקוני קו לכפתורים ולסימנים בממשק (מתן, 12.10).

עד אז חלק מהכפתורים היו אימוג'י — 📷 סריקה, 📅 תאריך, 📎 קבלה, 🔁 קבועה —
צבעוניים ובסגנון של מערכת ההפעלה, ליד אייקוני קו בזהב של האתר. עכשיו כולם
באותו קו. אימוג'י נשארים רק במה שהמשתמש בוחר בעצמו: קטגוריות ופרויקטים.

‎currentColor‎ — האייקון בצבע הטקסט שסביבו, ובגודל ‎1em‎ — בגודל הטקסט."""
from markupsafe import Markup

_PATHS = {
    "camera":   '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/>'
                '<circle cx="12" cy="13" r="3"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "receipt":  '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57'
                'a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
    "face":     '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/>'
                '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/>'
                '<path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>',
    "repeat":   '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/>'
                '<path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
}


def ui_icon(name: str) -> Markup:
    return Markup(
        '<svg class="ui-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false">{_PATHS[name]}</svg>')
