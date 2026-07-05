-- העדפות משפחה: אובייקט הגדרות גמיש לכל משפחה (שיוך לבני משפחה לפי סוג,
-- סף התראות חריגה, הצגת מקום עבודה). ברירות המחדל נמצאות בקוד השרת —
-- משפחה עם אובייקט ריק מקבלת את ההתנהגות ההיסטורית של האתר.
alter table public.families
  add column if not exists settings jsonb not null default '{}'::jsonb;
