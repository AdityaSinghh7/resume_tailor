-- 004_supabase_auth.sql

-- Add Supabase user id mapping for auth
ALTER TABLE users
ADD COLUMN IF NOT EXISTS supabase_uid UUID;

CREATE UNIQUE INDEX IF NOT EXISTS users_supabase_uid_unique
ON users (supabase_uid);

