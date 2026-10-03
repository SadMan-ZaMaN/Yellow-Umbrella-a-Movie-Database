from fastapi import APIRouter, Depends

from auth import check_owner_or_admin, get_current_user
from database import get_db

router = APIRouter(prefix="/stats", tags=["Stats & Analytics"])

# ── Uses DB Function: get_top_rated_media ────────────────────
@router.get("/top-rated")
def get_top_rated(limit: int = 10):
    """Top rated movies/series/anime/games by avgrating"""
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT * FROM get_top_rated_media(:l);", l=limit)
        return [{"id": r[0], "title": r[1],
                 "avgrating": float(r[2]) if r[2] else None,
                 "type": r[3], "posterurl": r[4]} for r in rows]
    finally:
        conn.close()

# ── Uses DB Function: get_most_reviewed ──────────────────────
@router.get("/most-reviewed")
def get_most_reviewed(limit: int = 10):
    """Media with the most number of user reviews"""
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT * FROM get_most_reviewed(:l);", l=limit)
        return [{"id": r[0], "title": r[1],
                 "review_count": r[2],
                 "avgrating": float(r[3]) if r[3] else None} for r in rows]
    finally:
        conn.close()

# ── Complex query: top rated by media type ───────────────────
@router.get("/top-rated/{mediatype}")
def get_top_rated_by_type(mediatype: str, limit: int = 10):
    """Top rated filtered by type — movie, series, anime, game"""
    if mediatype not in ("movie", "series", "anime", "game"):
        return {"error": "mediatype must be movie, series, anime or game"}
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT mediaid, title, avgrating, posterurl
               FROM media
               WHERE CASE 
                    WHEN EXISTS (SELECT 1 FROM movie WHERE movieid = media.mediaid) THEN 'movie'
                    WHEN EXISTS (SELECT 1 FROM series WHERE seriesid = media.mediaid) THEN 'series'
                    WHEN EXISTS (SELECT 1 FROM anime WHERE animeid = media.mediaid) THEN 'anime'
                    WHEN EXISTS (SELECT 1 FROM game WHERE gameid = media.mediaid) THEN 'game'
                    ELSE 'unknown'
                END = :mt AND avgrating IS NOT NULL
               ORDER BY avgrating DESC
               LIMIT :l;""", mt=mediatype, l=limit)
        return [{"id": r[0], "title": r[1],
                 "avgrating": float(r[2]) if r[2] else None,
                 "posterurl": r[3]} for r in rows]
    finally:
        conn.close()

# ── Complex query: most active users ─────────────────────────
@router.get("/most-active-users")
def get_most_active_users(limit: int = 10):
    """Users who have written the most reviews"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT u.userid, u.username,
                      COUNT(r.mediaid) AS review_count,
                      ROUND(AVG(r.rating)::DECIMAL, 2) AS avg_rating
               FROM users u
               JOIN review r ON u.userid = r.userid
               GROUP BY u.userid, u.username
               ORDER BY review_count DESC
               LIMIT :l;""", l=limit)
        return [{"userid": r[0], "username": r[1],
                 "review_count": r[2],
                 "avg_rating": float(r[3]) if r[3] else None} for r in rows]
    finally:
        conn.close()

# ── Complex query: most watchlisted media ────────────────────
@router.get("/most-watchlisted")
def get_most_watchlisted(limit: int = 10):
    """Media added to watchlists the most"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.mediatype,
                      m.avgrating, m.posterurl,
                      COUNT(w.userid) AS watchlist_count
               FROM media m
               JOIN watchlist w ON m.mediaid = w.mediaid
               GROUP BY m.mediaid
               ORDER BY watchlist_count DESC
               LIMIT :l;""", l=limit)
        return [{"id": r[0], "title": r[1], "type": r[2],
                 "avgrating": float(r[3]) if r[3] else None,
                 "posterurl": r[4], "watchlist_count": r[5]} for r in rows]
    finally:
        conn.close()

# ── Complex query: upcoming watch events ─────────────────────
@router.get("/upcoming-events")
def get_upcoming_events(limit: int = 5):
    """Next upcoming public watch events with RSVP counts"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT we.eventid, we.title, m.title, u.username,
                      we.platform, we.event_time,
                      COUNT(er.userid) AS rsvp_count
               FROM watch_event we
               JOIN media m  ON we.mediaid = m.mediaid
               JOIN users u  ON we.host_userid = u.userid
               LEFT JOIN event_rsvp er ON we.eventid = er.eventid
               WHERE we.ispublic = TRUE AND we.event_time > now()
               GROUP BY we.eventid, we.title, m.title,
                        u.username, we.platform, we.event_time
               ORDER BY we.event_time
               LIMIT :l;""", l=limit)
        return [{"eventid": r[0], "event_title": r[1],
                 "media": r[2], "host": r[3],
                 "platform": r[4], "time": str(r[5]),
                 "rsvp_count": r[6]} for r in rows]
    finally:
        conn.close()

# ── Uses DB Function: get_user_stats ─────────────────────────
@router.get("/user/{user_id}")
def get_user_stats(user_id: int, current_user: dict = Depends(get_current_user)):
    """A user's personal stats — reviews, watchlist, lists"""
    check_owner_or_admin(current_user, user_id)
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT * FROM get_user_stats(:id);", id=user_id)
        if not rows:
            return {"error": "User not found"}
        r = rows[0]
        return {
            "total_reviews": r[0],
            "avg_rating_given": float(r[1]) if r[1] else None,
            "watchlist_count": r[2],
            "lists_count": r[3]
        }
    finally:
        conn.close()
