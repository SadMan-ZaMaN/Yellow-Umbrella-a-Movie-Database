-- ============================================================
-- YellowUmbrella — triggers, functions and procedures
-- Run after schema.sql. Everything here is CREATE OR REPLACE,
-- so it's safe to re-run.
-- ============================================================


-- ============================================================
-- TRIGGER: keep media.avgrating in sync with its reviews
-- Fires on INSERT / UPDATE / DELETE, so the app never has to
-- recalculate averages itself.
-- ============================================================

CREATE OR REPLACE FUNCTION update_avg_rating()
RETURNS TRIGGER AS $$
DECLARE
    v_media_id INT;
BEGIN
    -- NEW exists for INSERT/UPDATE, OLD exists for DELETE
    v_media_id := COALESCE(NEW.mediaid, OLD.mediaid);

    UPDATE media
    SET avgrating = (
        SELECT ROUND(AVG(rating)::numeric, 2)
        FROM review
        WHERE mediaid = v_media_id
    )
    WHERE mediaid = v_media_id;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS rating_trigger ON review;

CREATE TRIGGER rating_trigger
AFTER INSERT OR UPDATE OR DELETE ON review
FOR EACH ROW EXECUTE FUNCTION update_avg_rating();


-- ============================================================
-- FUNCTIONS (used by routes/stats.py)
-- ============================================================

-- Top rated media of any type
CREATE OR REPLACE FUNCTION get_top_rated_media(limit_count INT)
RETURNS TABLE(mediaid INT, title VARCHAR, avgrating DECIMAL, mediatype VARCHAR, posterurl VARCHAR) AS $$
BEGIN
    RETURN QUERY
    SELECT m.mediaid, m.title, m.avgrating, m.mediatype, m.posterurl
    FROM media m
    WHERE m.avgrating IS NOT NULL
    ORDER BY m.avgrating DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- One user's activity summary
CREATE OR REPLACE FUNCTION get_user_stats(p_userid INT)
RETURNS TABLE(
    total_reviews    INT,
    avg_rating_given DECIMAL,
    watchlist_count  INT,
    lists_count      INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*)::INT FROM review WHERE userid = p_userid),
        (SELECT ROUND(AVG(rating)::DECIMAL, 2) FROM review WHERE userid = p_userid),
        (SELECT COUNT(*)::INT FROM watchlist WHERE userid = p_userid),
        (SELECT COUNT(*)::INT FROM customlist WHERE userid = p_userid);
END;
$$ LANGUAGE plpgsql;

-- Media with the most reviews
CREATE OR REPLACE FUNCTION get_most_reviewed(limit_count INT)
RETURNS TABLE(mediaid INT, title VARCHAR, review_count BIGINT, avgrating DECIMAL) AS $$
BEGIN
    RETURN QUERY
    SELECT m.mediaid, m.title, COUNT(r.userid) AS review_count, m.avgrating
    FROM media m
    JOIN review r ON m.mediaid = r.mediaid
    GROUP BY m.mediaid, m.title, m.avgrating
    ORDER BY review_count DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- PROCEDURES
-- A CALL runs inside the caller's transaction, so if any step
-- raises, every step before it is rolled back too. (An explicit
-- COMMIT inside an EXCEPTION block isn't allowed in PL/pgSQL.)
-- ============================================================

CREATE OR REPLACE PROCEDURE register_user(
    p_username VARCHAR,
    p_email    VARCHAR,
    p_password VARCHAR
)
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE LOWER(username) = LOWER(p_username)
                                      OR LOWER(email) = LOWER(p_email)) THEN
        RAISE EXCEPTION 'Username or email already taken';
    END IF;

    INSERT INTO users (username, email, password)
    VALUES (p_username, p_email, p_password);
END;
$$;

-- insert-or-update a review; avgrating is handled by the trigger
-- (ratings used to be whole numbers - drop that older signature so it
-- doesn't hang around as an overload)
DROP PROCEDURE IF EXISTS add_review(INT, INT, INT, TEXT);

CREATE OR REPLACE PROCEDURE add_review(
    p_mediaid     INT,
    p_userid      INT,
    p_rating      DECIMAL,
    p_commenttext TEXT
)
LANGUAGE plpgsql AS $$
BEGIN
    IF p_rating < 1 OR p_rating > 10 THEN
        RAISE EXCEPTION 'Rating must be between 1 and 10';
    END IF;

    INSERT INTO review (mediaid, userid, rating, commenttext)
    VALUES (p_mediaid, p_userid, p_rating, p_commenttext)
    ON CONFLICT (mediaid, userid) DO UPDATE
    SET rating      = EXCLUDED.rating,
        commenttext = EXCLUDED.commenttext,
        reviewdate  = CURRENT_DATE;
END;
$$;

-- remove a user and everything they own
CREATE OR REPLACE PROCEDURE delete_user(p_userid INT)
LANGUAGE plpgsql AS $$
BEGIN
    -- the foreign keys would cascade anyway; spelling it out keeps
    -- the order obvious and shows it happening in one transaction
    DELETE FROM event_rsvp     WHERE userid = p_userid;
    DELETE FROM watch_event    WHERE host_userid = p_userid;
    DELETE FROM media_comment  WHERE userid = p_userid;
    DELETE FROM person_comment WHERE userid = p_userid;
    DELETE FROM review_like    WHERE liker_userid = p_userid;
    DELETE FROM watchlist      WHERE userid = p_userid;
    DELETE FROM customlist     WHERE userid = p_userid;
    DELETE FROM review         WHERE userid = p_userid;
    DELETE FROM users          WHERE userid = p_userid;
END;
$$;
