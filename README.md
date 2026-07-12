# SmartFin – ניהול תקציב משפחתי

אפליקציית ווב (Mobile-First PWA) לניהול תקציב משפחתי משותף. עברית, RTL.
עיצוב "Gold Fintech": Hero כהה, כרטיסים לבנים צפים, מבטא זהב.

## סטאק

- **Backend:** Python + Flask (תבניות Jinja2)
- **Database & Auth:** Supabase (PostgreSQL + GoTrue, RLS מלא)
- **Frontend:** HTML + CSS מותאם + Vanilla JS + Chart.js
- **AI:** Anthropic Claude (סריקת קבלות)
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
│   │                           # projects, project_detail, login,
│   │                           # onboarding, reset_password, error
│   └── static/                 # style.css, sw.js, manifest.json, icons
├── tests/                      # בדיקות בידוד RLS (pytest)
├── docs/SPEC.md                # מסמך האפיון המלא
├── Procfile / runtime.txt      # הגדרות Railway
└── requirements.txt / requirements-dev.txt
```

## פיצ'רים

- **4 עמודים ראשיים:** בית (יתרת עו"ש + הוספה מהירה) · החודש (גרפים, פירוטים והתראות) · השוואה בין חודשים · הגדרות (אקורדיון)
- **עסקאות:** הוצאה / הכנסה / חיסכון, עם עריכה ומחיקה מכל מקום + החלקה (swipe) במובייל
- **שיוך לבן משפחה:** הוצאות והכנסות משויכות עם תגים בצבע קבוע לכל בן משפחה; חיסכון תמיד משפחתי
- **פרויקטים:** תקציבי פרויקט (טיול, שיפוץ...) — משותפים או אישיים, עם קטגוריות משלהם ויעד תקציב
- **עסקאות קבועות:** מנוע שמשלים מופעים אוטומטית — רטרואקטיבית וקדימה
- **סריקת קבלות:** צילום קבלה → זיהוי אוטומטי של סכום/תאריך/קטגוריה (Claude Vision)
- **התראות חריגה + תחזית:** קטגוריה שחורגת מממוצע 3 חודשים, ותחזית קצב-ריצה לפני שהחריגה קורית
- **משפחות:** קוד הזמנה, אונבורדינג לקביעת קטגוריות למשפחה חדשה
- **חשבון:** עריכת פרטים, שינוי סיסמה, שכחתי סיסמה, התחברות במייל או בטלפון,
  איפוס עסקאות ומחיקת חשבון לצמיתות (עם ארכיון פנימי לבעל האתר)
- **זכור אותי:** סשן 90 יום עם רענון טוקן אוטומטי

## הרצה מקומית

```bash
pip install -r requirements.txt
cp .env.example .env        # ומלא את המפתחות
flask --app backend.app run --port 8080
```

### משתני סביבה

| משתנה | תיאור |
|-------|-------|
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_KEY` | anon public key |
| `SECRET_KEY`   | מחרוזת אקראית לסשן Flask — **חובה, האפליקציה לא עולה בלעדיו** |
| `ANTHROPIC_API_KEY` | מפתח Anthropic — נדרש רק לסריקת קבלות (בלעדיו הסריקה לא פעילה) |
| `FLASK_ENV`    | `development` מקומית בלבד — **לא להגדיר בפרודקשן** (שולט בהקשחת עוגיות) |

## בדיקות

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

בדיקות בידוד ה-RLS רצות מול פרויקט ה-Supabase האמיתי עם שני חשבונות בדיקה
קבועים (ראה `tests/setup_rls_test_users.py` — הרצה חד-פעמית ליצירתם).

## מסד נתונים

הסכמה מנוהלת במלואה ב-`backend/supabase/migrations/`. לפרויקט Supabase חדש:

```bash
cd backend && supabase link --project-ref <REF> && supabase db push
```

טבלאות פנימיות לבעל האתר (לא נגישות למשתמשים, RLS ללא policies):
`owner_archive` — ארכיון כל מה שנמחק · `login_events` — תיעוד כניסות.

## פריסה ל-Railway

1. Push ל-GitHub → Railway → Deploy from GitHub repo
2. משתני סביבה: `SUPABASE_URL`, `SUPABASE_KEY`, `SECRET_KEY` (ערך אקראי חזק!),
   `ANTHROPIC_API_KEY` (אופציונלי — לסריקת קבלות). **לא** להגדיר `FLASK_ENV`.
3. **חשוב:** לעדכן ב-Supabase Auth את `SITE_URL` ו-`URI_ALLOW_LIST` לדומיין החדש (בשביל קישורי איפוס סיסמה)
