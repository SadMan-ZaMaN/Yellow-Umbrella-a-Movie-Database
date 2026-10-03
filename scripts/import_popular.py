"""
Fills the catalogue with titles people actually know: the most-voted movies
and shows on TMDB (the closest thing to "everyone has heard of it"), the most
popular anime, and the games most people own on RAWG. Already-imported
titles are skipped, so it's safe to re-run.

    python -m scripts.import_popular                 # ~350 titles, a few minutes
    python -m scripts.import_popular --pages 2       # fewer
"""
import sys
from concurrent.futures import ThreadPoolExecutor

from database import get_db
from services.importer import import_game, import_movie, import_tv, is_anime, rawg_get, tmdb_get

# TV genres that are mostly talk shows, news, soaps and reality TV
SKIP_TV_GENRES = {10763, 10764, 10766, 10767}


def popular_movies(pages):
    ids = []
    for page in range(1, pages + 1):
        data = tmdb_get("discover/movie", {"sort_by": "vote_count.desc", "page": page})
        ids += [("movie", m["id"]) for m in data["results"]]
    return ids


def popular_shows(pages):
    ids = []
    for page in range(1, pages + 1):
        data = tmdb_get("discover/tv", {"sort_by": "vote_count.desc", "page": page})
        ids += [("tv", s["id"]) for s in data["results"]
                if not SKIP_TV_GENRES & set(s.get("genre_ids", []))]
    return ids


def popular_anime(pages):
    ids = []
    for page in range(1, pages + 1):
        data = tmdb_get("discover/tv", {"with_genres": 16, "with_origin_country": "JP",
                                        "sort_by": "vote_count.desc", "page": page})
        ids += [("tv", s["id"]) for s in data["results"] if is_anime(s)]
    return ids


def popular_games(pages):
    ids = []
    for page in range(1, pages + 1):
        data = rawg_get("games", {"ordering": "-added", "page_size": 40, "page": page})
        ids += [("game", g["id"]) for g in data["results"]]
    return ids


IMPORTERS = {"movie": import_movie, "tv": import_tv, "game": import_game}


def import_one(item):
    kind, ext_id = item
    conn = get_db()
    try:
        # parallel imports can trip over each other creating the same
        # genre or actor; the second attempt finds it already there
        for attempt in range(3):
            try:
                IMPORTERS[kind](conn, ext_id)
                return True
            except Exception as e:
                if attempt == 2:
                    print(f"  failed {kind} {ext_id}: {e}")
    finally:
        conn.close()
    return False


def main(pages=5):
    wanted = (popular_movies(pages) + popular_shows(max(pages - 1, 1))
              + popular_anime(max(pages - 3, 1)) + popular_games(max(pages // 2, 1)))
    wanted = list(dict.fromkeys(wanted))    # same title can come from two lists
    print(f"Importing {len(wanted)} titles (already imported ones are skipped)...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        done = sum(pool.map(import_one, wanted))
    print(f"\nDone: {done}/{len(wanted)} ok")


if __name__ == "__main__":
    pages = int(sys.argv[sys.argv.index("--pages") + 1]) if "--pages" in sys.argv else 5
    main(pages)
