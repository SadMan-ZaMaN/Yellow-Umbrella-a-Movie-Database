-- ============================================================
-- YellowUmbrella — PostgreSQL schema
--
-- Covers: ISA hierarchies (Person, Media, Nomination), weak
-- entities (Season, Episode, Review, Trailer, CustomList), M:N
-- relationship tables, cascading deletes and join indexes.
--
-- Triggers, functions and procedures live in functions.sql.
--
--   psql -U postgres -d imdb_project -f sql/schema.sql
--   psql -U postgres -d imdb_project -f sql/functions.sql
-- ============================================================


-- ============================================================
-- 1) BASE / SUPPORT TABLES
-- ============================================================

CREATE TABLE users (
    userid      SERIAL PRIMARY KEY,
    username    VARCHAR(50)  UNIQUE NOT NULL,
    email       VARCHAR(255) UNIQUE NOT NULL,
    password    VARCHAR(255),                 -- pbkdf2 hash, see auth.py
    role        VARCHAR(20)  DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    photourl    VARCHAR(512),
    joindate    DATE DEFAULT CURRENT_DATE
);

CREATE TABLE genre (
    genreid     SERIAL PRIMARY KEY,
    genrename   VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE studio (
    studioid    SERIAL PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE country (
    countrycode CHAR(3) PRIMARY KEY,
    name        VARCHAR(255) NOT NULL
);

CREATE TABLE language (
    langid      SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE award_event (
    eventid     SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    imageurl    TEXT
);

CREATE TABLE award_category (
    categoryid  SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL
);


-- ============================================================
-- 2) PERSON ISA HIERARCHY (Person -> Actor, Director)
-- ============================================================

CREATE TABLE person (
    personid    SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    bio         TEXT,
    photourl    VARCHAR(512),
    birthdate   DATE
);

CREATE TABLE actor (
    actorid     INT PRIMARY KEY REFERENCES person(personid) ON DELETE CASCADE,
    agentname   VARCHAR(255),
    unionstatus VARCHAR(100)
);

CREATE TABLE director (
    directorid  INT PRIMARY KEY REFERENCES person(personid) ON DELETE CASCADE,
    guildid     VARCHAR(100)
);


-- ============================================================
-- 3) MEDIA ISA HIERARCHY (Media -> Movie, Series, Anime, Game)
-- mediatype duplicates which child table a row lives in; it makes
-- listing queries a lot simpler than four EXISTS checks.
-- ============================================================

CREATE TABLE media (
    mediaid     SERIAL PRIMARY KEY,
    title       VARCHAR(255) NOT NULL,
    releasedate DATE,
    avgrating   DECIMAL(4,2),                 -- kept up to date by rating_trigger
    posterurl   VARCHAR(512),
    mediatype   VARCHAR(20) DEFAULT 'movie'
                CHECK (mediatype IN ('movie', 'series', 'anime', 'game')),
    tmdb_id     INT UNIQUE,
    tmdb_rating DECIMAL(4,2),
    overview    TEXT
);

CREATE TABLE movie (
    movieid     INT PRIMARY KEY REFERENCES media(mediaid) ON DELETE CASCADE,
    durationmin INT CHECK (durationmin IS NULL OR durationmin > 0),
    boxoffice   DECIMAL(15,2)
);

CREATE TABLE series (
    seriesid     INT PRIMARY KEY REFERENCES media(mediaid) ON DELETE CASCADE,
    totalseasons INT CHECK (totalseasons IS NULL OR totalseasons >= 0),
    status       VARCHAR(20) CHECK (status IN ('Ongoing', 'Ended', 'Canceled') OR status IS NULL)
);

CREATE TABLE anime (
    animeid       INT PRIMARY KEY REFERENCES media(mediaid) ON DELETE CASCADE,
    totalseasons  INT,
    totalepisodes INT,
    studio_name   VARCHAR(255),               -- e.g. MAPPA, Ufotable
    status        VARCHAR(20) CHECK (status IN ('Ongoing', 'Ended', 'Canceled') OR status IS NULL)
);

CREATE TABLE game (
    gameid      INT PRIMARY KEY REFERENCES media(mediaid) ON DELETE CASCADE,
    developer   VARCHAR(255),
    publisher   VARCHAR(255),
    platform    VARCHAR(255),                 -- e.g. 'PC, PS5, Xbox'
    esrb_rating VARCHAR(10)                   -- e.g. 'M', 'T', 'E'
);


-- ============================================================
-- 4) NOMINATION ISA (Nomination -> Media_Nom, Person_Nom)
-- ============================================================

CREATE TABLE nomination (
    nominationid SERIAL PRIMARY KEY,
    eventid      INT NOT NULL REFERENCES award_event(eventid) ON DELETE RESTRICT,
    categoryid   INT NOT NULL REFERENCES award_category(categoryid) ON DELETE RESTRICT,
    year         INT NOT NULL CHECK (year >= 1800),
    iswinner     BOOLEAN DEFAULT FALSE
);

CREATE TABLE media_nom (
    nomid       INT PRIMARY KEY REFERENCES nomination(nominationid) ON DELETE CASCADE,
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE
);

CREATE TABLE person_nom (
    nomid       INT PRIMARY KEY REFERENCES nomination(nominationid) ON DELETE CASCADE,
    personid    INT NOT NULL REFERENCES person(personid) ON DELETE CASCADE
);


-- ============================================================
-- 5) WEAK ENTITIES — Season, Episode (identified by their series)
-- ============================================================

CREATE TABLE season (
    seriesid    INT NOT NULL REFERENCES series(seriesid) ON DELETE CASCADE,
    seasonnum   INT NOT NULL,
    title       VARCHAR(255),
    releasedate DATE,
    PRIMARY KEY (seriesid, seasonnum)
);

CREATE TABLE episode (
    seriesid      INT NOT NULL,
    seasonnum     INT NOT NULL,
    episodenumber INT NOT NULL,
    title         VARCHAR(255),
    duration      INT CHECK (duration IS NULL OR duration > 0),
    airdate       DATE,
    PRIMARY KEY (seriesid, seasonnum, episodenumber),
    FOREIGN KEY (seriesid, seasonnum) REFERENCES season(seriesid, seasonnum) ON DELETE CASCADE
);


-- ============================================================
-- 6) USER CONTENT
-- Review     — weak entity on (Media, User), one per user per title
-- Trailer    — weak entity on (Media, TrailerNum)
-- CustomList — weak entity on (User, ListName); private by default
-- ============================================================

CREATE TABLE review (
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    userid      INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    rating      DECIMAL(4,1) NOT NULL CHECK (rating BETWEEN 1 AND 10),
    commenttext TEXT,
    reviewdate  DATE DEFAULT CURRENT_DATE,
    PRIMARY KEY (mediaid, userid)
);

-- someone else replying to a review
CREATE TABLE comment (
    commentid        SERIAL PRIMARY KEY,
    mediaid          INT NOT NULL,
    review_userid    INT NOT NULL,           -- whose review this is on
    commenter_userid INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    commenttext      TEXT NOT NULL,
    createdat        TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (mediaid, review_userid) REFERENCES review(mediaid, userid) ON DELETE CASCADE
);

CREATE TABLE review_like (
    mediaid       INT NOT NULL,
    review_userid INT NOT NULL,
    liker_userid  INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    PRIMARY KEY (mediaid, review_userid, liker_userid),
    FOREIGN KEY (mediaid, review_userid) REFERENCES review(mediaid, userid) ON DELETE CASCADE
);

-- free-form discussion on a title / person page
CREATE TABLE media_comment (
    commentid   SERIAL PRIMARY KEY,
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    userid      INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    commenttext TEXT NOT NULL,
    createdat   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE person_comment (
    commentid   SERIAL PRIMARY KEY,
    personid    INT NOT NULL REFERENCES person(personid) ON DELETE CASCADE,
    userid      INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    commenttext TEXT NOT NULL,
    createdat   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE trailer (
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    trailernum  INT NOT NULL,
    title       VARCHAR(255),
    url         VARCHAR(512),
    PRIMARY KEY (mediaid, trailernum)
);

CREATE TABLE customlist (
    userid      INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    listname    VARCHAR(255) NOT NULL,
    description TEXT,
    ispublic    BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (userid, listname)
);

CREATE TABLE customlistitem (
    userid      INT NOT NULL,
    listname    VARCHAR(255) NOT NULL,
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    addedat     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (userid, listname, mediaid),
    FOREIGN KEY (userid, listname) REFERENCES customlist(userid, listname) ON DELETE CASCADE
);

CREATE TABLE watchlist (
    userid      INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    addedat     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (userid, mediaid)
);

-- when a user plans to watch something
CREATE TABLE schedule (
    scheduleid    SERIAL PRIMARY KEY,
    userid        INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    mediaid       INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    scheduledtime TIMESTAMPTZ NOT NULL,
    note          TEXT
);


-- ============================================================
-- 7) WATCH PARTIES — a user hosts, others RSVP
-- ============================================================

CREATE TABLE watch_event (
    eventid     SERIAL PRIMARY KEY,
    host_userid INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    title       VARCHAR(255) NOT NULL,         -- e.g. "Drive movie night!"
    description TEXT,
    platform    VARCHAR(100),                  -- 'Discord', 'Teleparty', ...
    event_time  TIMESTAMPTZ NOT NULL,
    stream_link VARCHAR(512),                  -- only shown to people who joined
    ispublic    BOOLEAN DEFAULT TRUE,
    createdat   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE event_rsvp (
    eventid     INT NOT NULL REFERENCES watch_event(eventid) ON DELETE CASCADE,
    userid      INT NOT NULL REFERENCES users(userid) ON DELETE CASCADE,
    status      VARCHAR(20) NOT NULL CHECK (status IN ('joined', 'interested')),
    rsvp_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (eventid, userid)
);


-- ============================================================
-- 8) M:N RELATIONSHIP TABLES
-- ============================================================

-- "cast" is a keyword, hence cast_member
CREATE TABLE cast_member (
    mediaid      INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    actorid      INT NOT NULL REFERENCES actor(actorid) ON DELETE CASCADE,
    rolename     VARCHAR(255),
    billingorder INT CHECK (billingorder IS NULL OR billingorder > 0),
    PRIMARY KEY (mediaid, actorid)
);

CREATE TABLE media_director (
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    directorid  INT NOT NULL REFERENCES director(directorid) ON DELETE CASCADE,
    PRIMARY KEY (mediaid, directorid)
);

CREATE TABLE media_genre (
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    genreid     INT NOT NULL REFERENCES genre(genreid) ON DELETE CASCADE,
    PRIMARY KEY (mediaid, genreid)
);

CREATE TABLE media_studio (
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    studioid    INT NOT NULL REFERENCES studio(studioid) ON DELETE CASCADE,
    PRIMARY KEY (mediaid, studioid)
);

CREATE TABLE media_country (
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    countrycode CHAR(3) NOT NULL REFERENCES country(countrycode) ON DELETE RESTRICT,
    PRIMARY KEY (mediaid, countrycode)
);

CREATE TABLE media_language (
    mediaid     INT NOT NULL REFERENCES media(mediaid) ON DELETE CASCADE,
    langid      INT NOT NULL REFERENCES language(langid) ON DELETE RESTRICT,
    PRIMARY KEY (mediaid, langid)
);


-- ============================================================
-- 9) INDEXES
-- Primary keys already cover lookups by their leading column,
-- these are for the other side of the common joins.
-- ============================================================

CREATE INDEX idx_review_user           ON review(userid);
CREATE INDEX idx_comment_review        ON comment(mediaid, review_userid);
CREATE INDEX idx_media_comment         ON media_comment(mediaid);
CREATE INDEX idx_person_comment        ON person_comment(personid);
CREATE INDEX idx_cast_actor            ON cast_member(actorid);
CREATE INDEX idx_media_director_dir    ON media_director(directorid);
CREATE INDEX idx_watchlist_media       ON watchlist(mediaid);
CREATE INDEX idx_season_series         ON season(seriesid);
CREATE INDEX idx_episode_season        ON episode(seriesid, seasonnum);
CREATE INDEX idx_media_genre_genre     ON media_genre(genreid);
CREATE INDEX idx_media_studio_studio   ON media_studio(studioid);
CREATE INDEX idx_media_country_country ON media_country(countrycode);
CREATE INDEX idx_media_language_lang   ON media_language(langid);
CREATE INDEX idx_schedule_user_time    ON schedule(userid, scheduledtime);
CREATE INDEX idx_watch_event_host      ON watch_event(host_userid);
CREATE INDEX idx_watch_event_media     ON watch_event(mediaid);
CREATE INDEX idx_event_rsvp_user       ON event_rsvp(userid);

-- no double-booking the same title at the same time
CREATE UNIQUE INDEX ux_schedule_unique ON schedule(userid, mediaid, scheduledtime);
