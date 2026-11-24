-- Players no longer pick a college; scores are individual. Mirrors the backend's own
-- `ALTER TABLE finishes DROP COLUMN IF EXISTS college` in infrastructure/postgres.py. Idempotent.
ALTER TABLE public.finishes DROP COLUMN IF EXISTS college;
