"""כפיל בזיכרון ל-PostgREST, למסלולים שמזיזים כסף.

הבדיקות על הכסף חייבות להריץ את הקוד האמיתי — את המסלול ב-‎app.py‎ ואת
הפונקציה ב-‎supabase_config.py‎ שהוא קורא לה — ולבדוק מה **באמת** נשמר.
לכן הזיוף יושב בשכבה התחתונה ביותר, במקום ‎get_client()‎, ולא מחליף את
פונקציות הכתיבה עצמן: אחרת הבדיקה מאמתת את הכפיל.

הכפיל מחקה את שלוש ההתנהגויות שעליהן הקוד באמת נשען:

1. ‎.data‎ אחרי ‎update‎/‎delete‎ מחזיר את השורות שנגעו בפועל, ורשימה
   ריקה כששום שורה לא התאימה (‎returning=representation‎ הוא ברירת
   המחדל). כל בדיקת "אף שורה לא נגעה" תלויה בזה.
2. ‎.eq()‎ מסנן באמת — כך שמזהה של משפחה אחרת לא מתאים לכלום, וזה מה
   שהופך בדיקת בידוד לאפשרית בלי מסד.
3. ‎insert‎ מחזיר את השורה כפי שנשמרה, כולל מה שהמסלול חישב.
"""
import itertools
import uuid


class FakeExecute:
    """מה ש-‎.execute()‎ מחזיר: ‎.data‎ ו-‎.count‎."""

    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, db, table):
        self._db = db
        self._table = table
        self._filters = []
        self._op = "select"
        self._payload = None
        self._count = None
        self._limit = None
        self._single = None
        self._order = None

    # ─── בניית השאילתה ──────────────────────────────────────────────────
    def select(self, *_a, count=None, **_k):
        self._op = "select"
        self._count = count
        return self

    def insert(self, payload, **_k):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload, **_k):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self, **_k):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self._filters.append(("neq", column, value))
        return self

    def gte(self, column, value):
        self._filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self._filters.append(("lte", column, value))
        return self

    def in_(self, column, values):
        self._filters.append(("in", column, list(values)))
        return self

    def is_(self, column, value):
        self._filters.append(("is", column, None if value == "null" else value))
        return self

    def order(self, column, desc=False, **_k):
        self._order = (column, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = "single"
        return self

    def maybe_single(self):
        self._single = "maybe"
        return self

    # ─── ההרצה ──────────────────────────────────────────────────────────
    def _matches(self, row):
        for kind, column, value in self._filters:
            actual = row.get(column)
            if kind == "eq" and actual != value:
                return False
            if kind == "neq" and actual == value:
                return False
            if kind == "gte" and not (actual is not None and str(actual) >= str(value)):
                return False
            if kind == "lte" and not (actual is not None and str(actual) <= str(value)):
                return False
            if kind == "in" and actual not in value:
                return False
            if kind == "is" and actual is not value:
                return False
        return True

    def execute(self):
        rows = self._db.tables.setdefault(self._table, [])

        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            created = []
            for item in payload:
                row = dict(item)
                row.setdefault("id", str(uuid.uuid4()))
                rows.append(row)
                created.append(dict(row))
            self._db.writes.append((self._table, "insert", created))
            return FakeExecute(created)

        hit = [r for r in rows if self._matches(r)]

        if self._op == "update":
            for row in hit:
                row.update(self._payload)
            touched = [dict(r) for r in hit]
            self._db.writes.append((self._table, "update", touched))
            return FakeExecute(touched)

        if self._op == "delete":
            removed = [dict(r) for r in hit]
            self._db.tables[self._table] = [r for r in rows if not self._matches(r)]
            self._db.writes.append((self._table, "delete", removed))
            return FakeExecute(removed)

        # select
        self._db.reads.append((self._table, len(hit)))
        if self._order:
            column, desc = self._order
            hit.sort(key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        total = len(hit)
        if self._limit is not None:
            hit = hit[:self._limit]
        if self._single == "single":
            if not hit:
                raise LookupError(f"{self._table}: single() לא מצא שורה")
            return FakeExecute(dict(hit[0]), total)
        if self._single == "maybe":
            return FakeExecute(dict(hit[0]) if hit else None, total)
        return FakeExecute([dict(r) for r in hit], total)


class FakeSupabase:
    """‎FakeSupabase(transactions=[...], families=[...])‎ — טבלאות בזיכרון.

    ‎writes‎ מתעד כל כתיבה לפי סדר, כדי שבדיקה תוכל לומר "לא נכתב כלום"
    ולא רק "התשובה הייתה שגיאה". זה ההבדל בין לתפוס ולידציה שמחזירה 422
    לבין לתפוס ולידציה שמחזירה 422 **אחרי** שכבר שמרה.
    """

    def __init__(self, **tables):
        self.tables = {name: [dict(r) for r in rows] for name, rows in tables.items()}
        self.writes = []
        self.reads = []
        self.rpcs = []
        self.rpc_results = {}
        self._ids = itertools.count(1)

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params=None):
        self.rpcs.append((name, dict(params or {})))
        return _Rpc(self.rpc_results.get(name))

    # ─── נוחות לבדיקות ──────────────────────────────────────────────────
    def rows(self, table):
        return [dict(r) for r in self.tables.get(table, [])]

    def written(self, table=None, op=None):
        return [w for w in self.writes
                if (table is None or w[0] == table) and (op is None or w[1] == op)]


class _Rpc:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return FakeExecute(self._result)
