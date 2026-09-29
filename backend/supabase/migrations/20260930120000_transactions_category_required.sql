/*
 * אין עסקה בלי קטגוריה — החלטה של מתן (30.9).
 *
 * עסקת בית חייבת ‎category_id‎, ועסקת פרויקט חייבת ‎project_category_id‎.
 * השרת כבר דוחה שמירה בלי קטגוריה, ומחיקת קטגוריה מעבירה את העסקאות
 * שלה לפני שהיא נמחקת. האילוץ הוא הרשת שמתחת: שני ה-FK הם ‎ON DELETE SET
 * NULL‎, אז עסקה שנוספה לקטגוריה בין ההעברה למחיקה — או כל מסלול עתידי
 * ששוכח להעביר — מכשיל את המחיקה במקום להשאיר עסקה יתומה.
 *
 * עשר העסקאות הישנות בלי קטגוריה שויכו לפני המיגרציה, לפי הבחירה של מתן.
 */
alter table public.transactions
    add constraint transactions_category_required check (
        case when project_id is null then category_id is not null
             else project_category_id is not null
        end
    );
