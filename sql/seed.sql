-- ============================================================
-- seed.sql — a small hand-written sample dataset
-- Enough to click around the site without any API keys.
-- Safe to re-run: it truncates everything first.
--
-- WARNING: this wipes ALL data, including real users.
-- ============================================================

BEGIN;

-- 1) Clear existing data (child tables first via CASCADE)
TRUNCATE TABLE
  cast_member,
  media_director,
  watchlist,
  media_genre,
  media_studio,
  media_country,
  media_language,
  customlistitem,
  customlist,
  schedule,
  trailer,
  review,
  episode,
  season,
  media_nom,
  person_nom,
  nomination,
  actor,
  director,
  person,
  movie,
  series,
  media,
  users,
  genre,
  studio,
  country,
  language,
  award_event,
  award_category,
  watch_event
RESTART IDENTITY CASCADE;

-- ============================================================
-- 2) BASE / SUPPORT TABLES
-- ============================================================

INSERT INTO users (userid, username, email, joindate) VALUES
  (1, 'ryan_gosling', 'ryan@imdb.local', '2026-01-10'),
  (2, 'mia_wallace',  'mia@imdb.local',  '2026-01-12'),
  (3, 'hannah_b',     'hannah@imdb.local','2026-01-20'),
  (4, 'saito_k',      'saito@imdb.local','2026-02-01');

INSERT INTO genre (genreid, genrename) VALUES
  (1, 'Drama'),
  (2, 'Sci-Fi'),
  (3, 'Action'),
  (4, 'Comedy'),
  (5, 'Thriller'),
  (6, 'Crime');

INSERT INTO studio (studioid, name) VALUES
  (1, 'Warner Bros'),
  (2, 'A24'),
  (3, 'Netflix'),
  (4, 'Paramount');

INSERT INTO country (countrycode, name) VALUES
  ('USA', 'United States'),
  ('CAN', 'Canada'),
  ('GBR', 'United Kingdom'),
  ('KOR', 'South Korea'),
  ('JPN', 'Japan');

INSERT INTO language (langid, name) VALUES
  (1, 'English'),
  (2, 'Korean'),
  (3, 'Japanese');

INSERT INTO award_event (eventid, name) VALUES
  (1, 'Academy Awards (Oscars)'),
  (2, 'Golden Globes');

INSERT INTO award_category (categoryid, name) VALUES
  (1, 'Best Picture'),
  (2, 'Best Actor'),
  (3, 'Best Director'),
  (4, 'Best TV Series');

-- ============================================================
-- 3) PERSON + ISA (Actor/Director)
-- ============================================================

INSERT INTO person (personid, name, bio, photourl, birthdate) VALUES
  (1, 'Ryan Gosling', 'Actor', NULL, '1980-11-12'),
  (2, 'Emma Stone', 'Actor', NULL, '1988-11-06'),
  (3, 'Ana de Armas', 'Actor', NULL, '1988-04-30'),
  (4, 'Harrison Ford', 'Actor', NULL, '1942-07-13'),
  (5, 'Denis Villeneuve', 'Director', NULL, '1967-10-03'),
  (6, 'Damien Chazelle', 'Director', NULL, '1985-01-19'),
  (7, 'Nicolas Winding Refn', 'Director', NULL, '1970-09-29'),
  (8, 'Carey Mulligan', 'Actor', NULL, '1985-05-28'),
  (9, 'John Legend', 'Actor', NULL, '1978-12-28'),
  (10, 'Steven Yeun', 'Actor', NULL, '1983-12-21'),
  (11, 'Ali Wong', 'Actor', NULL, '1982-04-19'),
  (12, 'Greta Lee', 'Actor', NULL, '1983-03-07');

-- Actors (subset of Person)
INSERT INTO actor (actorid, agentname, unionstatus) VALUES
  (1, 'CAA', 'SAG-AFTRA'),
  (2, 'WME', 'SAG-AFTRA'),
  (3, 'CAA', 'SAG-AFTRA'),
  (4, 'CAA', 'SAG-AFTRA'),
  (8, 'WME', 'SAG-AFTRA'),
  (9, 'CAA', 'SAG-AFTRA'),
  (10,'UTA', 'SAG-AFTRA'),
  (11,'UTA', 'SAG-AFTRA'),
  (12,'WME', 'SAG-AFTRA');

-- Directors (subset of Person)
INSERT INTO director (directorid, guildid) VALUES
  (5, 'DGA-55321'),
  (6, 'DGA-11327'),
  (7, 'DGA-99901');

-- ============================================================
-- 4) MEDIA + ISA (Movie/Series)
-- ============================================================

INSERT INTO media (mediaid, title, releasedate, avgrating, posterurl) VALUES
  (1, 'La La Land', '2016-12-09', NULL, NULL),
  (2, 'Blade Runner 2049', '2017-10-06', NULL, NULL),
  (3, 'Drive', '2011-09-16', NULL, NULL),
  (4, 'Past Lives', '2023-06-02', NULL, NULL),
  (5, 'Baby Driver', '2017-06-28', NULL, NULL),
  (6, 'Beef', '2023-04-06', NULL, NULL),
  (7, 'True Detective', '2014-01-12', NULL, NULL),
  (8, 'Arcane', '2021-11-06', NULL, NULL);

-- Movies
INSERT INTO movie (movieid, durationmin, boxoffice) VALUES
  (1, 128, 446100000.00),
  (2, 164, 267500000.00),
  (3, 100,  81000000.00),
  (4, 106,  42000000.00),
  (5, 113, 226900000.00);

-- Series
INSERT INTO series (seriesid, totalseasons, status) VALUES
  (6, 1, 'Ended'),
  (7, 4, 'Ongoing'),
  (8, 2, 'Ongoing');

UPDATE media SET mediatype = 'series' WHERE mediaid IN (SELECT seriesid FROM series);

-- ============================================================
-- 5) WEAK ENTITIES: Season + Episode
-- ============================================================

-- Beef (SeriesID=6)
INSERT INTO season (seriesid, seasonnum, title, releasedate) VALUES
  (6, 1, 'Season 1', '2023-04-06');

INSERT INTO episode (seriesid, seasonnum, episodenumber, title, duration, airdate) VALUES
  (6, 1, 1, 'Figures of Light', 34, '2023-04-06'),
  (6, 1, 2, 'The Rapture of Being Alive', 31, '2023-04-06'),
  (6, 1, 3, 'I Am Inhabited by a Cry', 33, '2023-04-06');

-- Arcane (SeriesID=8)
INSERT INTO season (seriesid, seasonnum, title, releasedate) VALUES
  (8, 1, 'Season 1', '2021-11-06'),
  (8, 2, 'Season 2', '2025-11-01');

INSERT INTO episode (seriesid, seasonnum, episodenumber, title, duration, airdate) VALUES
  (8, 1, 1, 'Welcome to the Playground', 41, '2021-11-06'),
  (8, 1, 2, 'Some Mysteries Are Better Left Unsolved', 39, '2021-11-06'),
  (8, 2, 1, 'Shadows of Zaun', 42, '2025-11-01');

-- ============================================================
-- 6) RELATIONSHIPS (Genres, Studios, Countries, Languages)
-- ============================================================

-- Media-Genre
INSERT INTO media_genre (mediaid, genreid) VALUES
  (1, 1), (1, 4),         -- La La Land: Drama, Comedy
  (2, 2), (2, 3), (2, 5), -- Blade Runner 2049: Sci-Fi, Action, Thriller
  (3, 6), (3, 5),         -- Drive: Crime, Thriller
  (4, 1),                 -- Past Lives: Drama
  (5, 3), (5, 6),         -- Baby Driver: Action, Crime
  (6, 1), (6, 4),         -- Beef: Drama, Comedy
  (7, 6), (7, 5),         -- True Detective: Crime, Thriller
  (8, 2), (8, 3);         -- Arcane: Sci-Fi, Action

-- Media-Studio
INSERT INTO media_studio (mediaid, studioid) VALUES
  (1, 4),
  (2, 1),
  (3, 2),
  (4, 2),
  (5, 4),
  (6, 3),
  (7, 1),
  (8, 3);

-- Media-Country
INSERT INTO media_country (mediaid, countrycode) VALUES
  (1, 'USA'),
  (2, 'USA'),
  (3, 'USA'),
  (4, 'USA'),
  (5, 'USA'),
  (6, 'USA'),
  (7, 'USA'),
  (8, 'USA');

-- Media-Language
INSERT INTO media_language (mediaid, langid) VALUES
  (1, 1),
  (2, 1),
  (3, 1),
  (4, 1),
  (5, 1),
  (6, 1),
  (7, 1),
  (8, 1);

-- ============================================================
-- 7) CAST + DIRECTORS (M:N)
-- ============================================================

-- Cast
INSERT INTO cast_member (mediaid, actorid, rolename, billingorder) VALUES
  (1, 1, 'Sebastian', 1),
  (1, 2, 'Mia', 2),
  (1, 9, 'Keith', 3),

  (2, 1, 'K', 1),
  (2, 3, 'Joi', 2),
  (2, 4, 'Deckard', 3),

  (3, 1, 'Driver', 1),
  (3, 8, 'Irene', 2),

  (4, 12, 'Nora', 1),

  (6, 10, 'Danny Cho', 1),
  (6, 11, 'Amy Lau', 2),

  (8, 12, 'Voice / Role', 1);

-- Directors
INSERT INTO media_director (mediaid, directorid) VALUES
  (1, 6), -- La La Land: Chazelle
  (2, 5), -- BR2049: Villeneuve
  (3, 7), -- Drive: Refn
  (4, 5), -- (demo)
  (5, 6), -- (demo)
  (6, 5); -- (demo)

-- ============================================================
-- 8) TRAILERS
-- ============================================================

INSERT INTO trailer (mediaid, trailernum, title, url) VALUES
  (1, 1, 'Official Trailer', 'https://example.com/lalaland-trailer'),
  (2, 1, 'Official Trailer', 'https://example.com/br2049-trailer'),
  (3, 1, 'Official Trailer', 'https://example.com/drive-trailer'),
  (6, 1, 'Official Trailer', 'https://example.com/beef-trailer');

-- ============================================================
-- 9) REVIEWS (Trigger updates media.avgrating automatically)
-- ============================================================

INSERT INTO review (mediaid, userid, rating, commenttext, reviewdate) VALUES
  (1, 1, 10, 'Perfect music + heartbreak.', '2026-02-02'),
  (1, 2,  9, 'Loved the songs and visuals.', '2026-02-03'),
  (1, 3,  8, 'Great, but bittersweet.', '2026-02-04'),

  (2, 1,  9, 'Atmosphere is unreal.', '2026-02-02'),
  (2, 2, 10, 'Masterpiece sci-fi.', '2026-02-03'),
  (2, 4,  9, 'Stunning cinematography.', '2026-02-05'),

  (3, 1,  8, 'Minimal, cold, iconic.', '2026-02-06'),
  (3, 2,  7, 'Slow but stylish.', '2026-02-06'),
  (3, 3,  9, 'Loved the vibe.', '2026-02-06'),
  (3, 4,  8, 'Great soundtrack.', '2026-02-07'),

  (6, 1,  9, 'Best series of the year.', '2026-02-08'),
  (6, 2,  8, 'Wild and emotional.', '2026-02-08'),
  (6, 3,  9, 'Relatable chaos.', '2026-02-08'),

  (8, 2,  9, 'Animation is insane.', '2026-02-09'),
  (8, 4, 10, 'Peak storytelling.', '2026-02-10');

-- ============================================================
-- 10) WATCHLIST, CUSTOM LISTS, SCHEDULE
-- ============================================================

-- Watchlist
INSERT INTO watchlist (userid, mediaid, addedat) VALUES
  (1, 2, now()),
  (1, 6, now()),
  (2, 1, now()),
  (2, 3, now()),
  (3, 8, now()),
  (4, 2, now());

-- Custom Lists
INSERT INTO customlist (userid, listname, description) VALUES
  (1, 'Weekend Watch', 'Stuff I will watch this weekend'),
  (2, 'Favorites', 'All-time favorites'),
  (3, 'Study Cinematography', 'Movies/series to learn visuals');

-- Custom List Items
INSERT INTO customlistitem (userid, listname, mediaid, addedat) VALUES
  (1, 'Weekend Watch', 6, now()),
  (1, 'Weekend Watch', 3, now()),
  (2, 'Favorites', 1, now()),
  (2, 'Favorites', 2, now()),
  (3, 'Study Cinematography', 2, now()),
  (3, 'Study Cinematography', 8, now());

-- Schedule (calendar)
INSERT INTO schedule (userid, mediaid, scheduledtime, note) VALUES
  (1, 6, '2026-02-12 21:00:00+06', 'Start Beef S1'),
  (1, 3, '2026-02-13 23:30:00+06', 'Late-night Drive vibes'),
  (2, 1, '2026-02-14 20:00:00+06', 'Rewatch with friends'),
  (3, 2, '2026-02-15 19:00:00+06', 'BR2049 study session');

-- ============================================================
-- 11) NOMINATIONS + ISA (Media_Nom / Person_Nom)
-- ============================================================

INSERT INTO nomination (nominationid, eventid, categoryid, year, iswinner) VALUES
  (1, 1, 1, 2017, TRUE),   -- Best Picture (example)
  (2, 1, 2, 2017, FALSE),  -- Best Actor
  (3, 1, 3, 2017, FALSE),  -- Best Director
  (4, 2, 4, 2023, TRUE);   -- Best TV Series

-- Media nominations
INSERT INTO media_nom (nomid, mediaid) VALUES
  (1, 1),  -- La La Land Best Picture
  (4, 6);  -- Beef Best TV Series

-- Person nominations
INSERT INTO person_nom (nomid, personid) VALUES
  (2, 1),  -- Ryan nominee Best Actor
  (3, 5);  -- Villeneuve nominee Best Director

-- ============================================================
-- 12) Fix sequences (because we inserted explicit IDs)
-- ============================================================

SELECT setval(pg_get_serial_sequence('users','userid'),      (SELECT COALESCE(MAX(userid),1) FROM users), true);
SELECT setval(pg_get_serial_sequence('genre','genreid'),     (SELECT COALESCE(MAX(genreid),1) FROM genre), true);
SELECT setval(pg_get_serial_sequence('studio','studioid'),   (SELECT COALESCE(MAX(studioid),1) FROM studio), true);
SELECT setval(pg_get_serial_sequence('language','langid'),   (SELECT COALESCE(MAX(langid),1) FROM language), true);
SELECT setval(pg_get_serial_sequence('award_event','eventid'), (SELECT COALESCE(MAX(eventid),1) FROM award_event), true);
SELECT setval(pg_get_serial_sequence('award_category','categoryid'), (SELECT COALESCE(MAX(categoryid),1) FROM award_category), true);
SELECT setval(pg_get_serial_sequence('person','personid'),   (SELECT COALESCE(MAX(personid),1) FROM person), true);
SELECT setval(pg_get_serial_sequence('media','mediaid'),     (SELECT COALESCE(MAX(mediaid),1) FROM media), true);
SELECT setval(pg_get_serial_sequence('nomination','nominationid'), (SELECT COALESCE(MAX(nominationid),1) FROM nomination), true);
SELECT setval(pg_get_serial_sequence('schedule','scheduleid'), (SELECT COALESCE(MAX(scheduleid),1) FROM schedule), true);

COMMIT;

-- Quick sanity checks (optional):
-- SELECT mediaid, title, avgrating FROM media ORDER BY mediaid;
-- SELECT * FROM review WHERE mediaid=1;
