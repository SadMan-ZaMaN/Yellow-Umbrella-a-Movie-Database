import os

import requests
from fastapi import APIRouter

from database import get_db
from services.importer import fetch_and_save_game

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
        # 1 — search DB first
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl
               FROM media m JOIN game g ON m.mediaid = g.gameid
               WHERE m.title ILIKE :q;""", q=f"%{q}%")

        if rows:
            return {"source": "database", "results": [
                {"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4]}
                for r in rows]}

        # 2 — not in DB, search RAWG
        res  = requests.get("https://api.rawg.io/api/games",
                            params={"key": os.getenv("RAWG_KEY"), "search": q}, timeout=15)
        data = res.json()
        rawg_results = data.get("results", [])

        if not rawg_results:
            return {"source": "not_found", "results": []}

        # 3 — save top 3 and return
        saved = []
        for item in rawg_results[:3]:
            try:
                mediaid = fetch_and_save_game(conn, item["id"])
                saved.append({
                    "id": mediaid,
                    "title": item.get("name"),
                    "releasedate": item.get("released"),
                    "avgrating": None,
                    "posterurl": item.get("background_image")
                })
            except Exception as e:
                print(f"[auto-import error] {e}")

        return {"source": "rawg_imported", "results": saved}

    finally:
        conn.close()

@router.get("/{game_id}")
def get_game_detail(game_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl,
                      g.developer, g.publisher, g.platform, g.esrb_rating
               FROM media m JOIN game g ON m.mediaid=g.gameid WHERE m.mediaid=:id;""",
            id=game_id)
        if not rows:
            return {"error": "Not found"}
        r = rows[0]
        result = {"id": r[0], "title": r[1], "releasedate": str(r[2]),
                  "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4],
                  "developer": r[5], "publisher": r[6], "platform": r[7], "esrb": r[8]}
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
