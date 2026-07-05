# SmartFin – ניהול תקציב משפחתי

אפליקציית ווב (Mobile-First PWA) לניהול תקציב משפחתי משותף. עברית, RTL.
עיצוב "Gold Fintech": Hero כהה, כרטיסים לבנים צפים, מבטא זהב.

## סטאק

- **Backend:** Python + Flask (תבניות Jinja2)
- **Database & Auth:** Supabase (PostgreSQL + GoTrue, RLS מלא)
- **Frontend:** HTML + CSS מותאם + Vanilla JS + Chart.js
- **Deployment:** Railway (מוכן, טרם נפרס)

## מבנה הפרויקט

```
SmartFin/
├── backend/
│   ├── app.py                  # כל ה-routes וה-API
│   ├── supabase_config.py      # שכבת ה-DB: שאילתות, אימות, מנוע עסקאות קבועות
│   └── supabase/migrations/    # מקור האמת של סכמת מסד הנתונים
├── frontend/
│   ├── templates/              # base, index, month, months, settings,
│   │                           # login, onboarding, reset_password, error
│   └── static/                 # style.css, sw.js, manifest.json, icons
├── docs/SPEC.md                # מסמך האפיון המלא
├── Procfile / runtime.txt      # הגדרות Railway
└── requirements.txt
```

## פיצ'רים

- **4 עמודים:** בית (יתרת עו"ש + הוספה מהירה) · החודש (גרפים, פירוטים והתראות חריגה) · השוואה בין חודשים · הגדרות (אקורדיון)
- **עסקאות:** הוצאה / הכנסה / חיסכון, עם עריכה ומחיקה מכל מקום
- **שיוך לבן משפחה:** הוצאות והכנסות משויכות (מתן/אור/משותפת) עם תגים צבעוניים; חיסכון תמיד משפחתי
- **עסקאות קבועות:** מנוע שמשלים מופעים אוטומטית — רטרואקטיבית וקדימה
- **התראות חריגה:** קטגוריה שחורגת 50%+ מממוצע 3 חודשים
- **משפחות:** קוד הזמנה, אונבורדינג לקביעת קטגוריות למשפחה חדשה
- **חשבון:** עריכת פרטים (שם, טלפון, מיקום עבודה), שינוי סיסמה, שכחתי סיסמה במייל
- **זכור אותי:** סשן 90 יום עם רענון טוקן אוטומטי

## הרצה מקומית

```bash
pip install -r requirements.txt
cp .env.example .env        # ומלא את מפתחות Supabase
flask --app backend.app run --port 8080
```

### משתני סביבה

| משתנה | תיאור |
|-------|-------|
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_KEY` | anon public key |
| `SECRET_KEY`   | מחרוזת אקראית לסשן Flask |

## מסד נתונים

הסכמה מנוהלת במלואה ב-`backend/supabase/migrations/`. לפרויקט Supabase חדש:

```bash
cd backend && supabase link --project-ref <REF> && supabase db push
```

## פריסה ל-Railway

1. Push ל-GitHub → Railway → Deploy from GitHub repo
2. משתני סביבה: `SUPABASE_URL`, `SUPABASE_KEY`, `SECRET_KEY`
3. **חשוב:** לעדכן ב-Supabase Auth את `SITE_URL` ו-`URI_ALLOW_LIST` לדומיין החדש (בשביל קישורי איפוס סיסמה)
