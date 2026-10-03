from fastapi import APIRouter

from database import get_db
from services.importer import fetch_and_save_series, tmdb_get

router = APIRouter(prefix="/anime", tags=["Anime"])

@router.get("/")
def get_all_anime():
    conn = get_db()
    try:
        rows = conn.run("""
            SELECT m.mediaid, m.title, m.releasedate, m.avgrating,
                   m.posterurl, a.totalseasons, a.totalepisodes, a.studio_name, a.status
            FROM media m JOIN anime a ON m.mediaid = a.animeid
            ORDER BY m.title;
        """)
        return [{"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4],
                 "totalseasons": r[5], "totalepisodes": r[6],
                 "studio": r[7], "status": r[8]} for r in rows]
    finally:
        conn.close()


@router.get("/search")
def search_anime(q: str):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl
               FROM media m JOIN anime a ON m.mediaid = a.animeid
               WHERE m.title ILIKE :q;""", q=f"%{q}%")

        if rows:
            return {"source": "database", "results": [
                {"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4]}
                for r in rows]}

        # Search TMDB filtered to Japanese animation
        tmdb = tmdb_get("search/tv", {"query": q})
        results = [r for r in tmdb.get("results", [])
                   if r.get("origin_country") and "JP" in r.get("origin_country", [])]

        if not results:
            return {"source": "not_found", "results": []}

        saved = []
        for item in results[:3]:
            try:
                mediaid = fetch_and_save_series(conn, item["id"], mediatype="anime")
                saved.append({"id": mediaid, "title": item.get("name"),
                               "releasedate": item.get("first_air_date"), "avgrating": None,
                               "posterurl": f"https://image.tmdb.org/t/p/w500{item['poster_path']}"
                                            if item.get("poster_path") else None})
            except Exception as e:
                print(f"[auto-import error] {e}")

        return {"source": "tmdb_imported", "results": saved}
    finally:
        conn.close()


@router.get("/{anime_id}")
def get_anime_detail(anime_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl,
                      a.totalseasons, a.totalepisodes, a.studio_name, a.status
               FROM media m JOIN anime a ON m.mediaid=a.animeid
               WHERE m.mediaid=:id;""", id=anime_id)
        if not rows:
            return {"error": "Not found"}
        r = rows[0]

        anime = {"id": r[0], "title": r[1], "releasedate": str(r[2]),
         "avgrating": float(r[3]) if r[3] else None,
         "posterurl": r[4], "totalseasons": r[5],
         "totalepisodes": r[6], "studio": r[7], "status": r[8]}

        seasons = conn.run(
            "SELECT seasonnum, title, releasedate FROM season WHERE seriesid=:id ORDER BY seasonnum;",
            id=anime_id)

        anime["seasons"] = [
            {"season": s[0], "title": s[1], "releasedate": str(s[2])}
            for s in seasons
        ]

        # total episodes (from episode table if available, else from anime table)
        ep_count = conn.run(
            "SELECT COUNT(*) FROM episode WHERE seriesid=:id;", id=anime_id)
        db_eps = ep_count[0][0] if ep_count else 0
        anime["totalepisodes"] = db_eps if db_eps > 0 else anime.get("totalepisodes", 0)

        genres = conn.run(
            "SELECT g.genrename FROM genre g JOIN media_genre mg ON g.genreid=mg.genreid WHERE mg.mediaid=:id;",
            id=anime_id)

        anime["genres"] = [g[0] for g in genres]

        cast = conn.run(
            """SELECT p.name, cm.rolename, p.photourl FROM cast_member cm
               JOIN person p ON cm.actorid=p.personid
               WHERE cm.mediaid=:id ORDER BY cm.billingorder;""", id=anime_id)
        anime["cast"] = [{"name": c[0], "role": c[1], "photourl": c[2]} for c in cast]

        trailers = conn.run(
            "SELECT title, url FROM trailer WHERE mediaid=:id;", id=anime_id)
        anime["trailers"] = [{"title": t[0], "url": t[1]} for t in trailers]

        return anime
    
    finally:
        conn.close()


@router.get("/{anime_id}/episodes/{season_num}")
def get_anime_episodes(anime_id: int, season_num: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT episodenumber, title, duration, airdate
               FROM episode
               WHERE seriesid=:sid AND seasonnum=:snum
               ORDER BY episodenumber;""",
            sid=anime_id, snum=season_num)

        return [{
            "episode": r[0],
            "title": r[1],
            "duration": r[2],
            "airdate": str(r[3])
        } for r in rows]

    finally:
        conn.close()


@router.get("/{anime_id}/trailer")
def get_anime_trailer(anime_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT trailernum, title, url FROM trailer WHERE mediaid=:id ORDER BY trailernum;",
            id=anime_id)

        if not rows:
            return {"error": "No trailer available"}

        return [{
            "trailernum": r[0],
            "title": r[1],
            "url": r[2]
        } for r in rows]

    finally:
        conn.close()
