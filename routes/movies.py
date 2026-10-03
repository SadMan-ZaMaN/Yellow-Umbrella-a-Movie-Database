from fastapi import APIRouter

from database import get_db

router = APIRouter(prefix="/movies", tags=["Movies"])

@router.get("/")
def get_all_movies():
    conn = get_db()
    try:
        rows = conn.run("""
            SELECT m.mediaid, m.title, m.releasedate, m.avgrating,
                   m.posterurl, mo.durationmin, mo.boxoffice
            FROM media m
            JOIN movie mo ON m.mediaid = mo.movieid
            ORDER BY m.title;
        """)
        return [{"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None,
                 "posterurl": r[4], "durationmin": r[5],
                 "boxoffice": float(r[6]) if r[6] else None} for r in rows]
    finally:
        conn.close()

@router.get("/search")
def search_movies(q: str):
    conn = get_db()
    try:
        # local titles only - /search also asks TMDB and RAWG
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating, m.posterurl
               FROM media m JOIN movie mo ON m.mediaid = mo.movieid
               WHERE m.title ILIKE :q ORDER BY m.avgrating DESC NULLS LAST;""",
            q=f"%{q}%")

        return {"source": "database", "results": [
            {"id": r[0], "title": r[1], "releasedate": str(r[2]),
             "avgrating": float(r[3]) if r[3] else None, "posterurl": r[4]}
            for r in rows]}

    finally:
        conn.close()

@router.get("/{movie_id}")
def get_movie_detail(movie_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT m.mediaid, m.title, m.releasedate, m.avgrating,
                      m.posterurl, mo.durationmin, mo.boxoffice, m.overview, m.backdropurl
               FROM media m JOIN movie mo ON m.mediaid = mo.movieid
               WHERE m.mediaid = :id;""", id=movie_id)
        if not rows:
            return {"error": "Not found"}
        r = rows[0]
        movie = {"id": r[0], "title": r[1], "releasedate": str(r[2]),
                 "avgrating": float(r[3]) if r[3] else None,
                 "posterurl": r[4], "durationmin": r[5],
                 "boxoffice": float(r[6]) if r[6] else None,
                 "overview": r[7], "backdropurl": r[8]}

        genres = conn.run(
            "SELECT g.genrename FROM genre g JOIN media_genre mg ON g.genreid=mg.genreid WHERE mg.mediaid=:id;",
            id=movie_id)
        movie["genres"] = [g[0] for g in genres]

        cast = conn.run(
            """SELECT p.name, cm.rolename, p.photourl, p.personid FROM cast_member cm
               JOIN person p ON cm.actorid=p.personid
               WHERE cm.mediaid=:id ORDER BY cm.billingorder NULLS LAST;""", id=movie_id)
        movie["cast"] = [{"name": c[0], "role": c[1], "photourl": c[2], "id": c[3]} for c in cast]

        directors = conn.run(
            """SELECT p.name, p.personid FROM media_director md
               JOIN person p ON md.directorid=p.personid WHERE md.mediaid=:id;""", id=movie_id)
        movie["directors"] = [{"name": d[0], "id": d[1]} for d in directors]

        trailers = conn.run(
            "SELECT title, url FROM trailer WHERE mediaid=:id;", id=movie_id)
        movie["trailers"] = [{"title": t[0], "url": t[1]} for t in trailers]

        return movie
    finally:
        conn.close()

@router.get("/{movie_id}/trailer")
def get_movie_trailer(movie_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT trailernum, title, url FROM trailer WHERE mediaid=:id ORDER BY trailernum;",
            id=movie_id)
        if not rows:
            return {"error": "No trailer available"}
        return [{"trailernum": r[0], "title": r[1], "url": r[2]} for r in rows]
    finally:
        conn.close()
