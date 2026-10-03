import requests
import pg8000.native
from dotenv import load_dotenv
import os
import time

load_dotenv()

TMDB_BASE = "https://api.themoviedb.org/3"
HEADERS   = {
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

def backfill_ratings(conn):
    # get all media with no avgrating
    media = conn.run("""
        SELECT mediaid, title, mediatype FROM media
        WHERE avgrating IS NULL
        ORDER BY title;
    """)
    print(f"Found {len(media)} items with no rating\n")

    for item in media:
        mediaid, title, mediatype = item[0], item[1], item[2]
        try:
            if mediatype == "movie":
                search = tmdb_get("search/movie", {"query": title})
                results = search.get("results", [])
                rating  = results[0].get("vote_average") if results else None
            elif mediatype in ("series", "anime"):
                search = tmdb_get("search/tv", {"query": title})
                results = search.get("results", [])
                rating  = results[0].get("vote_average") if results else None
            else:
                # games — RAWG uses a different rating scale
                rating = None

            if rating:
                conn.run("BEGIN")
                conn.run(
                    "UPDATE media SET avgrating=:r WHERE mediaid=:id;",
                    r=round(rating, 2), id=mediaid)
                conn.run("COMMIT")
                print(f"  ✓ {title} → {rating}")
            else:
                print(f"  ✗ No rating found: {title}")

            time.sleep(0.25)
        except Exception as e:
            conn.run("ROLLBACK")
            print(f"  ✗ Error for {title}: {e}")

if __name__ == "__main__":
    conn = get_db()
    try:
        backfill_ratings(conn)
        print("\n✅ Ratings backfill complete!")
    finally:
        conn.close()