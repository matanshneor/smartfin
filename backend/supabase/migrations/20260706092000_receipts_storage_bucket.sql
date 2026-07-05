-- Bucket פרטי לתמונות קבלה. הנתיב בכל קובץ הוא {family_id}/{uuid}.{ext} —
-- מדיניות הגישה משווה את תיקיית השורש בנתיב למשפחה של המשתמש המחובר,
-- כך שכל משפחה רואה ומעלה רק לתיקייה שלה.
insert into storage.buckets (id, name, public)
values ('receipts', 'receipts', false)
on conflict (id) do nothing;

create policy receipts_family_select on storage.objects
    for select to authenticated using (
        bucket_id = 'receipts'
        and (storage.foldername(name))[1] = (
            select family_id::text from public.profiles where id = auth.uid()
        )
    );

create policy receipts_family_insert on storage.objects
    for insert to authenticated with check (
        bucket_id = 'receipts'
        and (storage.foldername(name))[1] = (
            select family_id::text from public.profiles where id = auth.uid()
        )
    );

create policy receipts_family_delete on storage.objects
    for delete to authenticated using (
        bucket_id = 'receipts'
        and (storage.foldername(name))[1] = (
            select family_id::text from public.profiles where id = auth.uid()
        )
    );
