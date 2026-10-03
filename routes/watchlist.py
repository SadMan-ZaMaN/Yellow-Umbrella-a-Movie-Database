from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import check_owner, check_owner_or_admin, get_current_user
from database import get_db

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])

class WatchlistItem(BaseModel):
    userid: int
    mediaid: int

@router.get("/{user_id}")
def get_watchlist(user_id: int, current_user: dict = Depends(get_current_user)):
    check_owner_or_admin(current_user, user_id)
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.avgrating, m.posterurl,
                      CASE 
                    WHEN EXISTS (SELECT 1 FROM movie WHERE movieid = m.mediaid) THEN 'movie'
                    WHEN EXISTS (SELECT 1 FROM series WHERE seriesid = m.mediaid) THEN 'series'
                    WHEN EXISTS (SELECT 1 FROM anime WHERE animeid = m.mediaid) THEN 'anime'
                    WHEN EXISTS (SELECT 1 FROM game WHERE gameid = m.mediaid) THEN 'game'
                    ELSE 'unknown'
                END as mediatype, w.addedat
               FROM watchlist w JOIN media m ON w.mediaid=m.mediaid
               WHERE w.userid=:id ORDER BY w.addedat DESC;""", id=user_id)
        return [{"id": r[0], "title": r[1],
                 "avgrating": float(r[2]) if r[2] else None,
                 "posterurl": r[3], "type": r[4], "addedat": str(r[5])} for r in rows]
    finally:
        conn.close()


@router.post("/")
def add_to_watchlist(item: WatchlistItem, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, item.userid)
    conn = get_db()
    try:
        existing = conn.run(
            "SELECT 1 FROM watchlist WHERE userid=:u AND mediaid=:m;",
            u=item.userid, m=item.mediaid)
        if existing:
            return {"error": "Already in watchlist"}
        conn.run("BEGIN")
        conn.run("INSERT INTO watchlist (userid, mediaid) VALUES (:u, :m);",
                 u=item.userid, m=item.mediaid)
        conn.run("COMMIT")
        return {"status": "added"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to add to watchlist: " + str(e)}
    finally:
        conn.close()


@router.delete("/{user_id}/{media_id}")
def remove_from_watchlist(user_id: int, media_id: int, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, user_id)
    conn = get_db()
    try:
        conn.run("BEGIN")

        conn.run("DELETE FROM watchlist WHERE userid=:u AND mediaid=:m;",
                 u=user_id, m=media_id)
        conn.run("COMMIT")

        return {"status": "removed"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to remove from watchlist: " + str(e)}
    
    finally:
        conn.close()
