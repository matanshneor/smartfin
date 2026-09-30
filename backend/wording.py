"""ניסוח של "מספר + שם עצם" — כלל אחד לכל האפליקציה.

"1 חברים", "1 פרויקטים", "1 עסקאות יימחקו" — בעברית זה "חבר אחד",
"פרויקט אחד", "עסקה אחת". אותו כלל בדיוק חי בדפדפן (‎sfCount‎ ב-core.js).
"""


def count_of(n, one: str, many: str) -> str:
    """‎count_of(1, "חבר אחד", "חברים") → "חבר אחד"‎; ‎count_of(3, …) → "3 חברים"‎.
    ‎one‎ הוא הצירוף המלא ליחיד, כי המספר "אחד/אחת" תלוי במין של שם העצם."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    return one if n == 1 else f"{n} {many}"


def share_map(items) -> dict:
    """אחוז לכל פריט מסך הכול, בשלמים שמסתכמים ל-100 בדיוק (שיטת השארית
    הגדולה). עיגול רגיל של 62.5 ו-37.5 נתן 63% ו-38% — 101%, מספר שכל מי
    שבודק יראה. מקבל רשימת ‎{"name", "total"}‎ ומחזיר ‎{name: אחוז}‎."""
    items = [i for i in items if float(i.get("total") or 0) > 0]
    whole = sum(float(i["total"]) for i in items)
    if not whole:
        return {}
    raw = [(i["name"], float(i["total"]) / whole * 100) for i in items]
    floors = {name: int(p) for name, p in raw}
    short = 100 - sum(floors.values())
    for name, p in sorted(raw, key=lambda x: x[1] - int(x[1]), reverse=True)[:short]:
        floors[name] += 1
    return floors
