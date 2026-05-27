# SmartFin – ניהול תקציב משפחתי

אפליקציית ניהול תקציב משפחתי Mobile-First בנויה על Flask + Supabase.

## סטאק טכנולוגי
- **Frontend:** HTML5, Custom CSS3 (Mobile-First)
- **Backend:** Python + Flask
- **Database & Auth:** Supabase (PostgreSQL + Auth)
- **Deployment:** Railway

## מבנה הפרויקט

```
SmartFin/
├── backend/              # Python – Flask + Supabase
│   ├── app.py            # Routes + auth
│   ├── supabase_config.py
│   ├── schema.sql
│   ├── schema_functions.sql
│   └── supabase/migrations/
├── frontend/             # HTML + CSS + JS
│   ├── templates/        # Jinja2 templates
│   └── static/           # CSS, icons, PWA assets
├── Procfile
├── requirements.txt
└── runtime.txt
```

## הרצה מקומית

```bash
# 1. התקנת dependencies
pip install -r requirements.txt

# 2. הגדרת .env
cp .env.example .env
# ערוך את .env עם ה-credentials שלך

# 3. הרצת האפליקציה
FLASK_APP=backend.app flask run
```

## הגדרת Supabase

ה-schema כבר דחוף לפרויקט `smartfin-family-budget`.

לפרויקט חדש:
```bash
supabase link --project-ref <REF>
supabase db push
```

### משתני סביבה נדרשים

| משתנה | תיאור |
|-------|-------|
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_KEY` | anon public key מ-Supabase Dashboard |
| `SECRET_KEY` | מחרוזת אקראית לסשן Flask |
| `FLASK_ENV` | `development` / `production` |

## פריסה ל-Railway

1. Push קוד ל-GitHub
2. צור פרויקט ב-Railway ← **Deploy from GitHub repo**
3. הוסף משתני סביבה:
   - `SUPABASE_URL`, `SUPABASE_KEY`, `SECRET_KEY`
   - `FLASK_ENV=production`
4. Railway מזהה את `Procfile` אוטומטית ומריץ:
   ```
   gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
   ```


## פיצ'רים

- ✅ Auth (הרשמה / התחברות) עם Supabase
- ✅ ניהול משפחות + קוד הזמנה
- ✅ הוספת עסקאות (הוצאה / הכנסה / חיסכון)
- ✅ עסקאות חוזרות (חודשי, שבועי)
- ✅ סריקת קבלה מדומה עם אנימציה
- ✅ דשבורד חודשי עם סיכומים
- ✅ ניווט בין חודשים
- ✅ ארכיון חודשים היסטורי
- ✅ גרפים: עוגה (קטגוריות) + עמודות (מגמה) + פירוט לפי חבר
- ✅ ניהול קטגוריות מותאמות
- ✅ PWA (Add to Home Screen)
- ✅ Railway-ready
