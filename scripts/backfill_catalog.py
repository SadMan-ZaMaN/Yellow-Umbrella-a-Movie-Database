"""
Matches every title already in the database to its TMDB / RAWG entry and
refreshes it: external id, poster, backdrop, overview, rating, vote count and
popularity, plus cast / trailers / genres if it has none.

Titles imported before those columns existed have none of this, which is why
ratings looked random (RAWG's out-of-5 next to TMDB's out-of-10) and why
Top Rated was full of things with a single vote.

    python -m scripts.backfill_catalog
"""
import re
from concurrent.futures import ThreadPoolExecutor

from database import get_db
from services.importer import (fill_missing_details, game_fields, movie_fields, rawg_get,
                               save_media, tmdb_get, tv_fields)


def _norm(title):
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def match_tmdb(kind, title, year):
    """TMDB id with the same title (and roughly the same year), or None."""
    results = tmdb_get(f"search/{kind}", {"query": title}).get("results", [])
    name_key, date_key = ("title", "release_date") if kind == "movie" else ("name", "first_air_date")
    same_title = [r for r in results if _norm(r.get(name_key)) == _norm(title)]
    if year:
        # release dates on older rows are sometimes off by a year
        close = [r for r in same_title
                 if (r.get(date_key) or "")[:4].isdigit() and abs(int(r[date_key][:4]) - int(year)) <= 1]
        if close:
            return close[0]["id"]
    if same_title:
        return max(same_title, key=lambda r: r.get("vote_count") or 0)["id"]
    return None


def match_rawg(title):
    results = rawg_get("games", {"search": title, "search_precise": "true"}).get("results", [])
    same = [r for r in results if _norm(r.get("name")) == _norm(title)]
    return max(same, key=lambda r: r.get("added") or 0)["id"] if same else None


def refresh(row):
    mediaid, title, mediatype, released, tmdb_id, rawg_id = row
    year = str(released)[:4] if released else None
    conn = get_db()
    try:
        if mediatype == "game":
            rawg_id = rawg_id or match_rawg(title)
            if not rawg_id:
                return "unmatched", title
            fields, details, kind = game_fields(rawg_get(f"games/{rawg_id}")), None, "game"
        else:
            kind = "movie" if mediatype == "movie" else "tv"
            tmdb_id = tmdb_id or match_tmdb(kind, title, year)
            if not tmdb_id:
                return "unmatched", title
            details = tmdb_get(f"{kind}/{tmdb_id}", {"append_to_response": "credits,videos"})
            fields = movie_fields(details) if kind == "movie" else tv_fields(details, mediatype)

        conn.run("BEGIN")
        try:
            save_media(conn, mediaid, fields)
            if details:
                fill_missing_details(conn, mediaid, kind, details)
            conn.run("COMMIT")
        except Exception as e:
            conn.run("ROLLBACK")
            if "ux_media_tmdb" in str(e) or "rawg_id_key" in str(e):
                return "duplicate", title     # another row already is this title
            raise
        return "updated", title
    except Exception as e:
        return "error", f"{title}: {e}"
    finally:
        conn.close()


def main():
    conn = get_db()
    rows = conn.run("SELECT mediaid, title, mediatype, releasedate, tmdb_id, rawg_id FROM media ORDER BY mediaid;")
    conn.close()
    print(f"Refreshing {len(rows)} titles...")

    outcome = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for status, detail in pool.map(refresh, rows):
            outcome.setdefault(status, []).append(detail)

    for status, items in outcome.items():
        print(f"\n{status}: {len(items)}")
        if status != "updated":
            for item in items:
                print(f"   {item}")


if __name__ == "__main__":
    main()
