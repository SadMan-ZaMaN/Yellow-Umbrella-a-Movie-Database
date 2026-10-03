-- ============================================================
-- upgrade.sql — bring a database made from an older schema.sql
-- up to date. Safe to run more than once.
--
--   psql -U postgres -d imdb_project -f sql/upgrade.sql
--   psql -U postgres -d imdb_project -f sql/functions.sql
--   python -m scripts.backfill_catalog      (fills the new columns)
-- ============================================================

ALTER TABLE users  ADD COLUMN IF NOT EXISTS photourl VARCHAR(512);

ALTER TABLE person ADD COLUMN IF NOT EXISTS tmdb_id INT;
ALTER TABLE person ADD COLUMN IF NOT EXISTS credits_synced_at TIMESTAMPTZ;

ALTER TABLE person_nom ADD COLUMN IF NOT EXISTS subtitle VARCHAR(255);

ALTER TABLE media ADD COLUMN IF NOT EXISTS backdropurl VARCHAR(512);
ALTER TABLE media ADD COLUMN IF NOT EXISTS overview    TEXT;
ALTER TABLE media ADD COLUMN IF NOT EXISTS tmdb_id     INT;
ALTER TABLE media ADD COLUMN IF NOT EXISTS rawg_id     INT;
ALTER TABLE media ADD COLUMN IF NOT EXISTS tmdb_rating DECIMAL(4,2);
ALTER TABLE media ADD COLUMN IF NOT EXISTS vote_count  INT;
ALTER TABLE media ADD COLUMN IF NOT EXISTS popularity  DECIMAL(10,3);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'person_tmdb_id_key') THEN
        ALTER TABLE person ADD CONSTRAINT person_tmdb_id_key UNIQUE (tmdb_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'media_rawg_id_key') THEN
        ALTER TABLE media ADD CONSTRAINT media_rawg_id_key UNIQUE (rawg_id);
    END IF;
END $$;

-- tmdb_id used to be unique across every type, but a movie and a TV show
-- can share the same TMDB number
ALTER TABLE media DROP CONSTRAINT IF EXISTS media_tmdb_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_media_tmdb_movie ON media(tmdb_id) WHERE mediatype = 'movie';
CREATE UNIQUE INDEX IF NOT EXISTS ux_media_tmdb_tv    ON media(tmdb_id) WHERE mediatype IN ('series', 'anime');
CREATE INDEX IF NOT EXISTS idx_media_type_popularity  ON media(mediatype, popularity DESC);
