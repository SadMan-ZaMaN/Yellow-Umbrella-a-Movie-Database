import requests
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from database import get_db
from services import discover, importer

router = APIRouter(tags=["Search & Discover"])


@router.get("/search")
def search(q: str, limit: int = 30):
    """Search titles and people across our database, TMDB and RAWG."""
    q = q.strip()
    if len(q) < 2:
        return {"results": []}
    conn = get_db()
    try:
        return {"results": discover.search(conn, q, min(limit, 60))}
    finally:
        conn.close()


@router.get("/discover/trending")
def trending(type: str = "all", limit: int = 20):
    """What's popular this week. Falls back to our own most popular titles
    if TMDB/RAWG can't be reached."""
    conn = get_db()
    try:
        try:
            return {"source": "live", "results": discover.trending(conn, type, min(limit, 40))}
        except requests.RequestException as e:
            print(f"[trending] falling back to the database: {e}")
            return {"source": "database", "results": discover.popular_from_db(conn, type, limit)}
    finally:
        conn.close()


@router.get("/open/{kind}/{ext_id}")
def open_external(kind: str, ext_id: int):
    """Import a TMDB/RAWG title (or person) on first visit, then go to its page.
    Search results and trending items that aren't in the database link here."""
    conn = get_db()
    try:
        if kind == "movie":
            url = f"/movie.html?id={importer.import_movie(conn, ext_id)}"
        elif kind == "tv":
            mediaid = importer.import_tv(conn, ext_id)
            mediatype = conn.run("SELECT mediatype FROM media WHERE mediaid=:id;", id=mediaid)[0][0]
            url = f"/{mediatype}.html?id={mediaid}"
        elif kind == "game":
            url = f"/game.html?id={importer.import_game(conn, ext_id)}"
        elif kind == "person":
            url = f"/person.html?id={importer.import_person(conn, ext_id)}"
        else:
            return HTMLResponse("Unknown type", status_code=404)
    except requests.RequestException as e:
        print(f"[open] {kind} {ext_id}: {e}")
        return HTMLResponse(
            "<p style='font-family:sans-serif'>Couldn't load this title right now. "
            "<a href='javascript:history.back()'>Go back</a></p>", status_code=502)
    finally:
        conn.close()
    return RedirectResponse(url, status_code=303)
