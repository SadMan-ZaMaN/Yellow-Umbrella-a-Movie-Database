from fastapi import APIRouter

from database import get_db
from services.importer import fetch_and_save_series, tmdb_get

router = APIRouter(prefix="/series", tags=["Series"])

@router.get("/")
def get_all_series():
    conn = get_db()
    try:
        rows = conn.run("""
            SELECT m.mediaid, m.title, m.releasedate, m.avgrating,
                   m.posterurl, s.totalseasons, s.status
            FROM media m 
            JOIN series s ON m.mediaid = s.seriesid
            LEFT JOIN anime a ON m.mediaid = a.animeid
            WHERE a.animeid IS NULL
            ORDER BY m.title;
        """)
        return [{"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None,
                 "posterurl": r[4], "totalseasons": r[5], "status": r[6]} for r in rows]
    finally:
        conn.close()

# /search has to be declared before /{series_id}, otherwise FastAPI
# tries to parse "search" as an id
@router.get("/search")
def search_series(q: str):
    conn = get_db()
    try:
        # 1 — search DB first
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl
               FROM media m 
               JOIN series s ON m.mediaid = s.seriesid
               LEFT JOIN anime a ON m.mediaid = a.animeid
               WHERE m.title ILIKE :q AND a.animeid IS NULL;""", q=f"%{q}%")

        if rows:
            return {"source": "database", "results": [
                {"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4]}
                for r in rows]}

        # 2 — not in DB, search TMDB
        tmdb = tmdb_get("search/tv", {"query": q})
        tmdb_results = tmdb.get("results", [])

        if not tmdb_results:
            return {"source": "not_found", "results": []}

        # 3 — save top 3 and return
        saved = []
        for item in tmdb_results[:3]:
            try:
                mediaid = fetch_and_save_series(conn, item["id"], mediatype="series")
                saved.append({
                    "id": mediaid,
                    "title": item.get("name"),
                    "releasedate": item.get("first_air_date"),
                    "avgrating": None,
                    "posterurl": f"https://image.tmdb.org/t/p/w500{item['poster_path']}"
                                 if item.get("poster_path") else None
                })
            except Exception as e:
                print(f"[auto-import error] {e}")

        return {"source": "tmdb_imported", "results": saved}

    finally:
        conn.close()

@router.get("/{series_id}")
def get_series_detail(series_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating,
                      m.posterurl, s.totalseasons, s.status
               FROM media m JOIN series s ON m.mediaid=s.seriesid
               WHERE m.mediaid=:id;""", id=series_id)
        if not rows:
            return {"error": "Not found"}
        r = rows[0]
        show = {"id": r[0], "title": r[1], "releasedate": str(r[2]),
                "avgrating": float(r[3]) if r[3] else None,
                "posterurl": r[4], "totalseasons": r[5], "status": r[6]}

        seasons = conn.run(
            "SELECT seasonnum, title, releasedate FROM season WHERE seriesid=:id ORDER BY seasonnum;",
            id=series_id)
        show["seasons"] = [{"season": s[0], "title": s[1], "releasedate": str(s[2])} for s in seasons]

        # total episodes
        ep_count = conn.run(
            "SELECT COUNT(*) FROM episode WHERE seriesid=:id;", id=series_id)
        show["totalepisodes"] = ep_count[0][0] if ep_count else 0

        genres = conn.run(
            "SELECT g.genrename FROM genre g JOIN media_genre mg ON g.genreid=mg.genreid WHERE mg.mediaid=:id;",
            id=series_id)
        show["genres"] = [g[0] for g in genres]

        cast = conn.run(
            """SELECT p.name, cm.rolename, p.photourl FROM cast_member cm
               JOIN person p ON cm.actorid=p.personid
               WHERE cm.mediaid=:id ORDER BY cm.billingorder;""", id=series_id)
        show["cast"] = [{"name": c[0], "role": c[1], "photourl": c[2]} for c in cast]

        directors = conn.run(
            """SELECT p.name FROM media_director md
               JOIN person p ON md.directorid=p.personid WHERE md.mediaid=:id;""", id=series_id)
        show["directors"] = [d[0] for d in directors]

        trailers = conn.run(
            "SELECT title, url FROM trailer WHERE mediaid=:id;", id=series_id)
        show["trailers"] = [{"title": t[0], "url": t[1]} for t in trailers]

        return show
    finally:
        conn.close()

@router.get("/{series_id}/episodes/{season_num}")
def get_episodes(series_id: int, season_num: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT episodenumber, title, duration, airdate
               FROM episode WHERE seriesid=:sid AND seasonnum=:snum
               ORDER BY episodenumber;""", sid=series_id, snum=season_num)
        return [{"episode": r[0], "title": r[1], "duration": r[2],
                 "airdate": str(r[3])} for r in rows]
    finally:
        conn.close()


@router.get("/{series_id}/trailer")
def get_series_trailer(series_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT trailernum, title, url FROM trailer WHERE mediaid=:id ORDER BY trailernum;",
            id=series_id)
        if not rows:
            return {"error": "No trailer available"}
        return [{"trailernum": r[0], "title": r[1], "url": r[2]} for r in rows]
    finally:
        conn.close()
