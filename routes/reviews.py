from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import check_owner, get_current_user
from database import get_db

router = APIRouter(prefix="/reviews", tags=["Reviews"])

class ReviewCreate(BaseModel):
    mediaid: int
    userid: int
    rating: float
    commenttext: str = ""

class CommentCreate(BaseModel):
    mediaid: int
    review_userid: int
    commenter_userid: int
    commenttext: str


@router.get("/{media_id}")
def get_reviews(media_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT u.username, r.rating, r.commenttext, r.reviewdate,
                      r.userid,
                      (SELECT COUNT(*) FROM review_like rl
                       WHERE rl.mediaid=r.mediaid AND rl.review_userid=r.userid) AS likes
               FROM review r JOIN users u ON r.userid=u.userid
               WHERE r.mediaid=:id ORDER BY r.reviewdate DESC;""",
            id=media_id)
        reviews = []
        for r in rows:
            # get comments for this review
            comments = conn.run(
                """SELECT u.username, c.commenttext, c.createdat
                   FROM comment c JOIN users u ON c.commenter_userid=u.userid
                   WHERE c.mediaid=:mid AND c.review_userid=:uid
                   ORDER BY c.createdat;""",
                mid=media_id, uid=r[4])
            reviews.append({
                "username": r[0], "rating": r[1], "comment": r[2],
                "date": str(r[3]), "userid": r[4], "likes": r[5],
                "comments": [{"username": c[0], "text": c[1],
                               "at": str(c[2])} for c in comments]
            })
        return reviews
    finally:
        conn.close()


@router.post("/")
def add_or_update_review(review: ReviewCreate, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, review.userid)
    if not 1 <= review.rating <= 10:
        return {"error": "Rating must be 1-10"}
    conn = get_db()
    try:
        existing = conn.run(
            "SELECT 1 FROM review WHERE mediaid=:m AND userid=:u;",
            m=review.mediaid, u=review.userid)
        
        conn.run("BEGIN")

        if existing:
            conn.run(
                "UPDATE review SET rating=:r, commenttext=:c, reviewdate=CURRENT_DATE WHERE mediaid=:m AND userid=:u;",
                r=review.rating, c=review.commenttext, m=review.mediaid, u=review.userid)
            
            conn.run("COMMIT")
            return {"status": "updated"}
        conn.run(
            "INSERT INTO review (mediaid, userid, rating, commenttext) VALUES (:m, :u, :r, :c);",
            m=review.mediaid, u=review.userid, r=review.rating, c=review.commenttext)
        
        conn.run("COMMIT")
        return {"status": "created"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to add/update review: " + str(e)}

    finally:
        conn.close()


@router.delete("/{media_id}/{user_id}")
def delete_review(media_id: int, user_id: int, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, user_id)
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run("DELETE FROM review WHERE mediaid=:m AND userid=:u;",
                 m=media_id, u=user_id)
        conn.run("COMMIT")
        return {"status": "deleted"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to delete review: " + str(e)}

    finally:
        conn.close()


@router.post("/like")
def like_review(mediaid: int, review_userid: int, liker_userid: int, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, liker_userid)
    conn = get_db()
    try:
        existing = conn.run(
            "SELECT 1 FROM review_like WHERE mediaid=:m AND review_userid=:r AND liker_userid=:l;",
            m=mediaid, r=review_userid, l=liker_userid)
        
        conn.run("BEGIN")
        if existing:
            conn.run(
                "DELETE FROM review_like WHERE mediaid=:m AND review_userid=:r AND liker_userid=:l;",
                m=mediaid, r=review_userid, l=liker_userid)
            conn.run("COMMIT")
            return {"status": "unliked"}
        conn.run(
            "INSERT INTO review_like (mediaid, review_userid, liker_userid) VALUES (:m, :r, :l);",
            m=mediaid, r=review_userid, l=liker_userid)
        conn.run("COMMIT")
        return {"status": "liked"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to like review: " + str(e)}
    finally:
        conn.close()


@router.post("/comment")
def add_comment(comment: CommentCreate, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, comment.commenter_userid)
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            """INSERT INTO comment (mediaid, review_userid, commenter_userid, commenttext)
               VALUES (:m, :r, :c, :t);""",
            m=comment.mediaid, r=comment.review_userid,
            c=comment.commenter_userid, t=comment.commenttext)
        conn.run("COMMIT")
        return {"status": "comment added"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to add comment: " + str(e)}
    finally:
        conn.close()
