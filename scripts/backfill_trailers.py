import requests
import pg8000.native
from dotenv import load_dotenv
import os
import time

load_dotenv()

TMDB_BASE = "https://api.themoviedb.org/3"
HEADERS = {
    "Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}",
    "accept": "application/json"
}

def get_db():
    return pg8000.native.Connection(
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT"))
    )

def tmdb_get(path, params={}):
    res = requests.get(f"{TMDB_BASE}/{path}", headers=HEADERS, params=params)
    res.raise_for_status()
    return res.json()

def save_trailers(conn, mediaid, tmdb_results, media_type):
    trailernum = 1
    for video in tmdb_results:
        if video.get("site") == "YouTube" and video.get("type") == "Trailer":
            existing = conn.run(
                "SELECT 1 FROM trailer WHERE mediaid=:m AND trailernum=:n;",
                m=mediaid, n=trailernum)
            if not existing:
                conn.run(
                    "INSERT INTO trailer (mediaid, trailernum, title, url) VALUES (:m, :n, :t, :u);",
                    m=mediaid, n=trailernum,
                    t=video.get("name", "Official Trailer"),
                    u=f"https://www.youtube.com/embed/{video['key']}")
            trailernum += 1
            if trailernum > 3:
                break

def backfill_movies(conn):
    print("\nBackfilling movie trailers...")
    # get all movies that have no trailer yet
    movies = conn.run("""
        SELECT mo.movieid, m.title
        FROM movie mo
        JOIN media m ON mo.movieid = m.mediaid
        WHERE mo.movieid NOT IN (SELECT DISTINCT mediaid FROM trailer)
        ORDER BY m.title;
    """)
    print(f"  Found {len(movies)} movies without trailers")
    for movie in movies:
        mediaid, title = movie[0], movie[1]
        try:
            # search TMDB by title to get tmdb_id
            search = tmdb_get("search/movie", {"query": title})
            results = search.get("results", [])
            if not results:
                print(f"  ✗ Not found on TMDB: {title}")
                continue
            tmdb_id = results[0]["id"]
            # fetch videos
            videos = tmdb_get(f"movie/{tmdb_id}/videos")
            save_trailers(conn, mediaid, videos.get("results", []), "movie")
            print(f"  ✓ {title}")
            time.sleep(0.3)   # be polite to API
        except Exception as e:
            print(f"  ✗ Error for {title}: {e}")

def backfill_series(conn):
    print("\nBackfilling series/anime trailers...")
    # get all series+anime that have no trailer yet
    shows = conn.run("""
        SELECT m.mediaid, m.title
        FROM media m
        WHERE m.mediatype IN ('series', 'anime')
        AND m.mediaid NOT IN (SELECT DISTINCT mediaid FROM trailer)
        ORDER BY m.title;
    """)
    print(f"  Found {len(shows)} shows without trailers")
    for show in shows:
        mediaid, title = show[0], show[1]
        try:
            search = tmdb_get("search/tv", {"query": title})
            results = search.get("results", [])
            if not results:
                print(f"  ✗ Not found on TMDB: {title}")
                continue
            tmdb_id = results[0]["id"]
            videos = tmdb_get(f"tv/{tmdb_id}/videos")
            save_trailers(conn, mediaid, videos.get("results", []), "tv")
            print(f"  ✓ {title}")
            time.sleep(0.3)
        except Exception as e:
            print(f"  ✗ Error for {title}: {e}")

if __name__ == "__main__":
    conn = get_db()
    try:
        backfill_movies(conn)
        backfill_series(conn)
        print("\n✅ Trailer backfill complete!")
    finally:
        conn.close()