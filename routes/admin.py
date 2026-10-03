from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import require_admin
from database import get_db

router = APIRouter(prefix="/admin", tags=["Admin"])

# ── Models ───────────────────────────────────────────────────

class MediaUpdate(BaseModel):
    title:       str  = None
    releasedate: str  = None
    posterurl:   str  = None
    mediatype:   str  = None

class MovieUpdate(BaseModel):
    durationmin: int   = None
    boxoffice:   float = None

class TrailerAdd(BaseModel):
    mediaid:    int
    trailernum: int
    title:      str
    url:        str  # YouTube embed URL

class MediaAdd(BaseModel):
    title:       str
    releasedate: str  = None
    posterurl:   str  = None
    mediatype:   str  = "movie"
    # movie specific
    durationmin: int   = None
    boxoffice:   float = None
    # series/anime specific
    totalseasons: int  = None
    status:       str  = None
    # game specific
    developer:  str = None
    publisher:  str = None
    platform:   str = None
    # anime specific
    totalepisodes: int = None
    studio_name:   str = None

# ── Dashboard — overview stats ────────────────────────────────
@router.get("/dashboard")
def admin_dashboard(current_user: dict = Depends(require_admin)):
    """Quick overview of everything in the DB"""
    conn = get_db()
    try:
        stats = {}

        # total counts
        stats["total_media"]    = conn.run("SELECT COUNT(*) FROM media;")[0][0]
        stats["total_movies"]   = conn.run("SELECT COUNT(*) FROM movie;")[0][0]
        stats["total_series"]   = conn.run("SELECT COUNT(*) FROM series;")[0][0]
        stats["total_anime"]    = conn.run("SELECT COUNT(*) FROM anime;")[0][0]
        stats["total_games"]    = conn.run("SELECT COUNT(*) FROM game;")[0][0]
        stats["total_users"]    = conn.run("SELECT COUNT(*) FROM users;")[0][0]
        stats["total_reviews"]  = conn.run("SELECT COUNT(*) FROM review;")[0][0]
        stats["total_comments"] = conn.run("SELECT COUNT(*) FROM media_comment;")[0][0]
        stats["total_events"]   = conn.run("SELECT COUNT(*) FROM watch_event;")[0][0]

        # recent activity
        recent_reviews = conn.run("""
            SELECT u.username, m.title, r.rating, r.reviewdate
            FROM review r
            JOIN users u ON r.userid=u.userid
            JOIN media m ON r.mediaid=m.mediaid
            ORDER BY r.reviewdate DESC LIMIT 5;
        """)
        stats["recent_reviews"] = [
            {"user": r[0], "media": r[1],
             "rating": r[2], "date": str(r[3])}
            for r in recent_reviews
        ]

        recent_users = conn.run("""
            SELECT userid, username, email, joindate, role
            FROM users ORDER BY joindate DESC LIMIT 5;
        """)
        stats["recent_users"] = [
            {"id": r[0], "username": r[1],
             "email": r[2], "joined": str(r[3]), "role": r[4]}
            for r in recent_users
        ]

        return stats
    finally:
        conn.close()

# ── Media management ──────────────────────────────────────────

@router.post("/media/add")
def admin_add_media(
    data: MediaAdd,
    current_user: dict = Depends(require_admin)
):
    """Manually add any media to the DB"""
    conn = get_db()
    try:
        # check duplicate
        existing = conn.run(
            "SELECT mediaid FROM media WHERE title=:t;", t=data.title)
        if existing:
            return {"error": f"'{data.title}' already exists in DB",
                    "mediaid": existing[0][0]}

        conn.run("BEGIN")

        # insert into media
        conn.run(
            """INSERT INTO media (title, releasedate, posterurl, mediatype)
               VALUES (:t, :r, :p, :mt);""",
            t=data.title, r=data.releasedate,
            p=data.posterurl, mt=data.mediatype)

        mediaid = conn.run(
            "SELECT mediaid FROM media WHERE title=:t;",
            t=data.title)[0][0]

        # insert into the right ISA table
        if data.mediatype == "movie":
            conn.run(
                "INSERT INTO movie (movieid, durationmin, boxoffice) VALUES (:id, :d, :b);",
                id=mediaid, d=data.durationmin, b=data.boxoffice)

        elif data.mediatype == "series":
            conn.run(
                "INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st);",
                id=mediaid, ts=data.totalseasons, st=data.status)

        elif data.mediatype == "anime":
            conn.run(
                """INSERT INTO anime
                   (animeid, totalseasons, totalepisodes, studio_name, status)
                   VALUES (:id, :ts, :te, :sn, :st);""",
                id=mediaid, ts=data.totalseasons,
                te=data.totalepisodes, sn=data.studio_name,
                st=data.status)

        elif data.mediatype == "game":
            conn.run(
                """INSERT INTO game (gameid, developer, publisher, platform)
                   VALUES (:id, :dev, :pub, :pl);""",
                id=mediaid, dev=data.developer,
                pub=data.publisher, pl=data.platform)

        conn.run("COMMIT")
        return {"status": "added", "mediaid": mediaid}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

@router.patch("/media/{media_id}")
def admin_update_media(
    media_id: int,
    data: MediaUpdate,
    current_user: dict = Depends(require_admin)
):
    """Update title, releasedate, posterurl, mediatype"""
    conn = get_db()
    try:
        # only update fields that were actually sent
        updates = {}
        if data.title:       updates["title"]       = data.title
        if data.releasedate: updates["releasedate"]  = data.releasedate
        if data.posterurl:   updates["posterurl"]    = data.posterurl
        if data.mediatype:   updates["mediatype"]    = data.mediatype

        if not updates:
            return {"error": "Nothing to update"}

        # build dynamic SET clause
        set_clause = ", ".join([f"{k}=:{k}" for k in updates])
        updates["id"] = media_id

        conn.run("BEGIN")
        conn.run(
            f"UPDATE media SET {set_clause} WHERE mediaid=:id;",
            **updates)
        conn.run("COMMIT")
        return {"status": "updated"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

@router.patch("/media/{media_id}/poster")
def admin_update_poster(
    media_id: int,
    posterurl: str,
    current_user: dict = Depends(require_admin)
):
    """Update just the poster URL of any media"""
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "UPDATE media SET posterurl=:p WHERE mediaid=:id;",
            p=posterurl, id=media_id)
        conn.run("COMMIT")
        return {"status": "poster updated"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

@router.delete("/media/{media_id}")
def admin_delete_media(
    media_id: int,
    current_user: dict = Depends(require_admin)
):
    """
    Delete any movie/series/anime/game from DB.
    Cascades automatically delete: reviews, watchlist,
    cast, trailers, genres, nominations etc.
    """
    conn = get_db()
    try:
        # get title for confirmation message
        rows = conn.run(
            "SELECT title FROM media WHERE mediaid=:id;", id=media_id)
        if not rows:
            return {"error": "Media not found"}
        title = rows[0][0]

        conn.run("BEGIN")
        conn.run("DELETE FROM media WHERE mediaid=:id;", id=media_id)
        conn.run("COMMIT")
        return {"status": "deleted", "title": title}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

# ── Trailer management ────────────────────────────────────────

@router.post("/trailer/add")
def admin_add_trailer(
    data: TrailerAdd,
    current_user: dict = Depends(require_admin)
):
    """Manually add a trailer URL for any media"""
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            """INSERT INTO trailer (mediaid, trailernum, title, url)
               VALUES (:m, :n, :t, :u)
               ON CONFLICT (mediaid, trailernum) DO UPDATE
               SET title=:t, url=:u;""",
            m=data.mediaid, n=data.trailernum,
            t=data.title, u=data.url)
        conn.run("COMMIT")
        return {"status": "trailer added/updated"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

@router.delete("/trailer/{media_id}/{trailernum}")
def admin_delete_trailer(
    media_id: int,
    trailernum: int,
    current_user: dict = Depends(require_admin)
):
    """Delete a specific trailer"""
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "DELETE FROM trailer WHERE mediaid=:m AND trailernum=:n;",
            m=media_id, n=trailernum)
        conn.run("COMMIT")
        return {"status": "trailer deleted"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

# ── User management ───────────────────────────────────────────

@router.get("/users")
def admin_get_all_users(current_user: dict = Depends(require_admin)):
    """See all users"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT userid, username, email, joindate, role
               FROM users ORDER BY joindate DESC;""")
        return [{"id": r[0], "username": r[1], "email": r[2],
                 "joindate": str(r[3]), "role": r[4]} for r in rows]
    finally:
        conn.close()

@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    """
    Permanently delete a user and ALL their data.
    Cascades handle: reviews, watchlist, lists, events, rsvps, comments.
    """
    conn = get_db()
    try:
        # prevent admin from deleting themselves
        if current_user["userid"] == user_id:
            return {"error": "You cannot delete your own admin account"}

        rows = conn.run(
            "SELECT username FROM users WHERE userid=:id;", id=user_id)
        if not rows:
            return {"error": "User not found"}
        username = rows[0][0]

        conn.run("BEGIN")
        # explicit deletes to show transaction control
        conn.run("DELETE FROM event_rsvp   WHERE userid=:id;", id=user_id)
        conn.run("DELETE FROM media_comment WHERE userid=:id;", id=user_id)
        conn.run("DELETE FROM person_comment WHERE userid=:id;", id=user_id)
        conn.run("DELETE FROM review_like   WHERE liker_userid=:id;", id=user_id)
        conn.run("DELETE FROM watchlist     WHERE userid=:id;", id=user_id)
        conn.run("DELETE FROM customlist    WHERE userid=:id;", id=user_id)
        conn.run("DELETE FROM review        WHERE userid=:id;", id=user_id)
        conn.run("DELETE FROM watch_event   WHERE host_userid=:id;", id=user_id)
        conn.run("DELETE FROM users         WHERE userid=:id;", id=user_id)
        conn.run("COMMIT")
        return {"status": "deleted", "username": username}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

@router.patch("/users/{user_id}/role")
def admin_change_role(
    user_id: int,
    role: str,
    current_user: dict = Depends(require_admin)
):
    """Promote a user to admin or demote back to user"""
    if role not in ("user", "admin"):
        return {"error": "role must be 'user' or 'admin'"}
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "UPDATE users SET role=:r WHERE userid=:id;",
            r=role, id=user_id)
        conn.run("COMMIT")
        return {"status": "role updated", "role": role}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

# ── Review management ─────────────────────────────────────────

@router.get("/reviews")
def admin_get_all_reviews(current_user: dict = Depends(require_admin)):
    """See all reviews across all media"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT u.username, m.title, r.rating,
                      r.commenttext, r.reviewdate,
                      r.mediaid, r.userid
               FROM review r
               JOIN users u ON r.userid=u.userid
               JOIN media m ON r.mediaid=m.mediaid
               ORDER BY r.reviewdate DESC;""")
        return [{"username": r[0], "media": r[1],
                 "rating": r[2], "comment": r[3],
                 "date": str(r[4]), "mediaid": r[5],
                 "userid": r[6]} for r in rows]
    finally:
        conn.close()

@router.delete("/reviews/{media_id}/{user_id}")
def admin_delete_review(
    media_id: int,
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    """Delete any review"""
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "DELETE FROM review WHERE mediaid=:m AND userid=:u;",
            m=media_id, u=user_id)
        conn.run("COMMIT")
        return {"status": "review deleted"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

# ── Comment management ────────────────────────────────────────

@router.get("/comments")
def admin_get_all_comments(current_user: dict = Depends(require_admin)):
    """See all media comments"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT mc.commentid, u.username, m.title,
                      mc.commenttext, mc.createdat
               FROM media_comment mc
               JOIN users u ON mc.userid=u.userid
               JOIN media m ON mc.mediaid=m.mediaid
               ORDER BY mc.createdat DESC;""")
        return [{"commentid": r[0], "username": r[1],
                 "media": r[2], "text": r[3],
                 "at": str(r[4])} for r in rows]
    finally:
        conn.close()

@router.delete("/comments/media/{comment_id}")
def admin_delete_media_comment(
    comment_id: int,
    current_user: dict = Depends(require_admin)
):
    """Delete any media comment"""
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "DELETE FROM media_comment WHERE commentid=:id;",
            id=comment_id)
        conn.run("COMMIT")
        return {"status": "comment deleted"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

@router.delete("/comments/person/{comment_id}")
def admin_delete_person_comment(
    comment_id: int,
    current_user: dict = Depends(require_admin)
):
    """Delete any person comment"""
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "DELETE FROM person_comment WHERE commentid=:id;",
            id=comment_id)
        conn.run("COMMIT")
        return {"status": "comment deleted"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

# ── Event management ──────────────────────────────────────────

@router.get("/events")
def admin_get_all_events(current_user: dict = Depends(require_admin)):
    """See all watch events"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT we.eventid, u.username, m.title,
                      we.title, we.platform, we.event_time,
                      we.ispublic,
                      (SELECT COUNT(*) FROM event_rsvp er
                       WHERE er.eventid=we.eventid) AS rsvp_count
               FROM watch_event we
               JOIN users u ON we.host_userid=u.userid
               JOIN media m ON we.mediaid=m.mediaid
               ORDER BY we.event_time DESC;""")
        return [{"id": r[0], "host": r[1], "media": r[2],
                 "title": r[3], "platform": r[4],
                 "time": str(r[5]), "public": r[6],
                 "rsvp_count": r[7]} for r in rows]
    finally:
        conn.close()

@router.delete("/events/{event_id}")
def admin_delete_event(
    event_id: int,
    current_user: dict = Depends(require_admin)
):
    """Delete any watch event"""
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "DELETE FROM watch_event WHERE eventid=:id;",
            id=event_id)
        conn.run("COMMIT")
        return {"status": "event deleted"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": str(e)}
    finally:
        conn.close()

# ── Search anything ───────────────────────────────────────────

@router.get("/search/media")
def admin_search_media(
    q: str,
    current_user: dict = Depends(require_admin)
):
    """Search media by title — for admin to find what to edit/delete"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, 
                CASE 
                    WHEN EXISTS (SELECT 1 FROM movie WHERE movieid = m.mediaid) THEN 'movie'
                    WHEN EXISTS (SELECT 1 FROM series WHERE seriesid = m.mediaid) THEN 'series'
                    WHEN EXISTS (SELECT 1 FROM anime WHERE animeid = m.mediaid) THEN 'anime'
                    WHEN EXISTS (SELECT 1 FROM game WHERE gameid = m.mediaid) THEN 'game'
                    ELSE 'unknown'
                END as mediatype,
                m.avgrating, m.posterurl
               FROM media m WHERE REPLACE(m.title, ' ', '') ILIKE :q
               ORDER BY m.title LIMIT 20;""",
            q=f"%{q.replace(' ', '')}%")
        return [{"id": r[0], "title": r[1], "type": r[2],
                 "avgrating": float(r[3]) if r[3] else None,
                 "posterurl": r[4]} for r in rows]
    finally:
        conn.close()

@router.get("/search/users")
def admin_search_users(
    q: str,
    current_user: dict = Depends(require_admin)
):
    """Search users by username"""
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT userid, username, email, joindate, role
               FROM users WHERE username ILIKE :q
               ORDER BY username;""",
            q=f"%{q}%")
        return [{"id": r[0], "username": r[1], "email": r[2],
                 "joindate": str(r[3]), "role": r[4]} for r in rows]
    finally:
        conn.close()
