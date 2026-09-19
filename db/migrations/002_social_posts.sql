-- 002_social_posts.sql
-- One row per (WordPress post, channel) published by social/publisher.py.
--
-- Written BEFORE the WordPress tags are swapped, so a post that published but
-- failed to re-tag is recognized on the next run and never published twice.
-- The unique constraint is the backstop for the same guarantee.
-- Works for any WordPress post (case-law or commentary); no court_opinions row
-- is required.

create table if not exists public.social_posts (
    id            bigint generated always as identity primary key,
    wp_post_id    bigint      not null,
    channel       text        not null,          -- 'threads' | 'facebook' | ...
    audience      text        not null,          -- 'attorneys' | 'public'
    remote_id     text        not null,          -- id returned by the platform
    permalink     text,
    content       jsonb,                         -- exactly what was posted
    case_key      text,                          -- set for case-law posts
    published_at  timestamptz not null default now(),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (wp_post_id, channel)
);
