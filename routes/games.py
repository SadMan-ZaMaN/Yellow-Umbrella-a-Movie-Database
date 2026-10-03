from fastapi import APIRouter

from database import get_db

router = APIRouter(prefix="/games", tags=["Games"])

@router.get("/")
def get_all_games():
    conn = get_db()
    try:
        rows = conn.run("""
            SELECT m.mediaid, m.title, m.releasedate, m.avgrating,
                   m.posterurl, g.developer, g.publisher, g.platform, g.esrb_rating
            FROM media m JOIN game g ON m.mediaid = g.gameid
            ORDER BY m.title;
        """)
        return [{"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4],
                 "developer": r[5], "publisher": r[6],
                 "platform": r[7], "esrb": r[8]} for r in rows]
    finally:
        conn.close()

@router.get("/search")
def search_games(q: str):
    conn = get_db()
    try:
        # local titles only - /search also asks TMDB and RAWG
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl
               FROM media m JOIN game g ON m.mediaid = g.gameid
               WHERE m.title ILIKE :q;""", q=f"%{q}%")

        return {"source": "database", "results": [
            {"id": r[0], "title": r[1], "releasedate": str(r[2]),
             "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4]}
            for r in rows]}

    finally:
        conn.close()

@router.get("/{game_id}")
def get_game_detail(game_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl,
                      g.developer, g.publisher, g.platform, g.esrb_rating, m.overview, m.backdropurl
               FROM media m JOIN game g ON m.mediaid=g.gameid WHERE m.mediaid=:id;""",
            id=game_id)
        if not rows:
            return {"error": "Not found"}
        r = rows[0]
        result = {"id": r[0], "title": r[1], "releasedate": str(r[2]),
                  "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4],
                  "developer": r[5], "publisher": r[6], "platform": r[7], "esrb": r[8],
                  "overview": r[9], "backdropurl": r[10]}
        genres = conn.run(
            "SELECT g.genrename FROM genre g JOIN media_genre mg ON g.genreid=mg.genreid WHERE mg.mediaid=:id;",
            id=game_id)
        result["genres"] = [g[0] for g in genres]

        trailers = conn.run(
            "SELECT title, url FROM trailer WHERE mediaid=:id;", id=game_id)
        result["trailers"] = [{"title": t[0], "url": t[1]} for t in trailers]

        return result
    finally:
        conn.close()
