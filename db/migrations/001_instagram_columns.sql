-- 001_instagram_columns.sql
-- Instagram carousel publishing (instagram/publisher.py).
--
-- instagram_media_id is written BEFORE the WordPress tags are swapped, so a
-- post that published but failed to re-tag is never published twice.
-- instagram_content keeps the exact slide text + caption that went out, so any
-- carousel can be re-rendered after its images are deleted from storage.
--
-- Run once in the Supabase SQL editor BEFORE deploying code that includes the
-- new CourtOpinion fields: several code paths write whole-row model dumps, and
-- they fail if these columns are missing.

alter table public.court_opinions
    add column if not exists instagram_media_id   text,
    add column if not exists instagram_permalink  text,
    add column if not exists instagram_content    jsonb,
    add column if not exists instagram_published_at timestamptz;
