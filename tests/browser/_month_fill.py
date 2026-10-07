"""עסקאות מילוי לעמוד החודש (7.10).

מאז 5.10 עמוד החודש מציג 5 עסקאות אחרונות, ו"לכל עסקאות החודש"
(‎#txScreenOpen‎) מופיע רק כשיש יותר מ-5. סקריפטים שיצרו עסקה או שתיים
וחיכו לכפתור — נתקעו. ‎fill_month‎ משלימה עד שיש יותר מ-5. החשבונות
זמניים (‎_accounts‎), אז אין מה לנקות.
"""
import datetime
import json


def fill_month(page, base, count=6, desc="FILL"):
    cats = page.request.get(base + "/api/categories").json()
    cat = next(c["id"] for c in cats if c["type"] == "expense")
    for i in range(count):
        page.request.fetch(base + "/api/transactions", method="POST", headers={"Content-Type": "application/json"},
                           data=json.dumps({"amount": 1 + i, "type": "expense", "category_id": cat,
                                            "description": desc, "date": datetime.date.today().isoformat()}))
