"""לוגים של האפליקציה.

הקוד השתמש ב-print בלבד — 61 קריאות, רובן בתוך except. הפלט הזה הולך
לבאפר הלוגים של Railway, שנמחק, ואף אחד לא קורא אותו. חשוב מכך: **Sentry
לא ראה אותו**. חיברנו ניטור שגיאות ואז ניתבנו סביבו את מצב הכשל הנפוץ
ביותר באפליקציה — שאילתה שנכשלת ונבלעת.

עם logging, השילוב של Sentry עם מודול הלוגים תופס אוטומטית כל רשומה
ברמת ERROR ומעלה והופך אותה לאירוע, ורשומות נמוכות יותר לפירורי-לחם
שנצמדים לאירוע הבא. כלומר: אותה שורת קוד, אבל עכשיו רואים אותה.

logger.exception (ולא logger.error) בתוך except — הוא מצרף את ה-traceback
המלא, שהוא בדיוק מה שחסר כדי לדעת למה השאילתה נכשלה.
"""
import logging
import os
import sys


def setup():
    """מכוון את הלוגים ל-stderr, שם Railway אוסף אותם.

    נקרא פעם אחת מ-app.py. ‎force=True‎ כי gunicorn כבר נגע בהגדרות
    הלוגים לפני שהאפליקציה נטענה, ובלעדיו ההגדרה כאן נבלעת בשקט."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    # רועשות מדי ברמת INFO, ולא מוסיפות דבר על מה שאנחנו כבר מתעדים
    for noisy in ("httpx", "hpack", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
