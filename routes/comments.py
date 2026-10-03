from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import check_owner, get_current_user
from database import get_db

router = APIRouter(prefix="/comments", tags=["Comments"])

class MediaComment(BaseModel):
    mediaid: int
    userid: int
    commenttext: str

class PersonComment(BaseModel):
    personid: int
    userid: int
    commenttext: str

# ── Comments on a movie/series/anime/game page ───────────────

@router.get("/media/{media_id}")
def get_media_comments(media_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT mc.commentid, u.username, mc.commenttext, mc.createdat
               FROM media_comment mc
               JOIN users u ON mc.userid = u.userid
               WHERE mc.mediaid = :id
               ORDER BY mc.createdat DESC;""", id=media_id)
        return [{"commentid": r[0], "username": r[1],
                 "text": r[2], "at": str(r[3])} for r in rows]
    finally:
        conn.close()

@router.post("/media")
def add_media_comment(c: MediaComment, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, c.userid)
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "INSERT INTO media_comment (mediaid, userid, commenttext) VALUES (:m, :u, :t);",
            m=c.mediaid, u=c.userid, t=c.commenttext)
        conn.run("COMMIT")
        return {"status": "comment added"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to add comment: " + str(e)}
    
    finally:
        conn.close()

@router.delete("/media/{comment_id}")
def delete_media_comment(comment_id: int, userid: int, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, userid)
    conn = get_db()
    try:
        conn.run("BEGIN")
        # Only the owner can delete their comment
        conn.run(
            "DELETE FROM media_comment WHERE commentid=:c AND userid=:u;",
            c=comment_id, u=userid)
        conn.run("COMMIT")
        return {"status": "deleted"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to delete comment: " + str(e)}
    finally:
        conn.close()

# ── Comments on an actor/director page ───────────────────────

@router.get("/person/{person_id}")
def get_person_comments(person_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT pc.commentid, u.username, pc.commenttext, pc.createdat
               FROM person_comment pc
               JOIN users u ON pc.userid = u.userid
               WHERE pc.personid = :id
               ORDER BY pc.createdat DESC;""", id=person_id)
        return [{"commentid": r[0], "username": r[1],
                 "text": r[2], "at": str(r[3])} for r in rows]
    finally:
        conn.close()

@router.post("/person")
def add_person_comment(c: PersonComment, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, c.userid)
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "INSERT INTO person_comment (personid, userid, commenttext) VALUES (:p, :u, :t);",
            p=c.personid, u=c.userid, t=c.commenttext)
        conn.run("COMMIT")
        return {"status": "comment added"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to add comment: " + str(e)}
    finally:
        conn.close()

@router.delete("/person/{comment_id}")
def delete_person_comment(comment_id: int, userid: int, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, userid)
    conn = get_db()
    try:
        conn.run("BEGIN")
        # Only the owner can delete their comment
        conn.run(
            "DELETE FROM person_comment WHERE commentid=:c AND userid=:u;",
            c=comment_id, u=userid)
        conn.run("COMMIT")
        return {"status": "deleted"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to delete comment: " + str(e)}
    
    finally:
        conn.close()
