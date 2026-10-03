import os
import pg8000.native
from dotenv import load_dotenv

import requests
from services.importer import tmdb_get, fetch_and_save_movie, fetch_and_save_series, fetch_and_save_game, RAWG_BASE

load_dotenv()

def get_db():
    return pg8000.native.Connection(
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "imdb_project")
    )

def clean_database():
    print("WARNING: Truncating core tables (media, person, award_event) cascading to all rels...")
    conn = get_db()
    try:
        # We also truncate award_event so we can cleanly re-seed the awards from scratch
        conn.run("TRUNCATE TABLE media, person, genre, studio, award_event RESTART IDENTITY CASCADE;")
        print("Database wiped and identities restarted.")
    finally:
        conn.close()

def import_trending_movies(limit=40):
    print(f"Importing top {limit} trending movies...")
    conn = get_db()
    try:
        data = tmdb_get("trending/movie/week")
        count = 0
        for item in data.get("results", []):
            if count >= limit:
                break
            # Skip items with no poster to ensure aesthetic grid
            if not item.get("poster_path"):
                continue
            try:
                fetch_and_save_movie(conn, item["id"])
                count += 1
            except Exception as e:
                print(f"Error fetching movie {item.get('title')}: {e}")
    finally:
        conn.close()

def import_trending_series(limit=40):
    print(f"Importing top {limit} trending series...")
    conn = get_db()
    try:
        data = tmdb_get("trending/tv/week")
        count = 0
        for item in data.get("results", []):
            if count >= limit:
                break
            if not item.get("poster_path"):
                continue
            try:
                # Let's decide if it's anime or series based on genre
                is_anime = False
                for gid in item.get("genre_ids", []):
                    if gid == 16: # Animation in TMDB
                        # Actually TMDB groups western animation here too, but for simplicity let's stick to 'series' unless it originates from JP
                        if 'JP' in item.get("origin_country", []):
                            is_anime = True
                            break
                            
                fetch_and_save_series(conn, item["id"], mediatype="anime" if is_anime else "series")
                count += 1
            except Exception as e:
                print(f"Error fetching series {item.get('name')}: {e}")
    finally:
        conn.close()

def import_trending_games(limit=20):
    print(f"Importing top {limit} popular games from RAWG...")
    conn = get_db()
    try:
        res = requests.get(f"{RAWG_BASE}/games", params={
            "key": os.getenv("RAWG_KEY"),
            "ordering": "-rating",
            "page_size": limit * 2 # Fetch more to filter out ones without background_image
        })
        if res.status_code != 200:
            print("Failed to fetch games from RAWG. Check API key.")
            return

        data = res.json()
        count = 0
        for item in data.get("results", []):
            if count >= limit:
                break
            if not item.get("background_image"):
                continue
            try:
                fetch_and_save_game(conn, item["id"])
                count += 1
            except Exception as e:
                print(f"Error fetching game {item.get('name')}: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clean_database()
    import_trending_movies(40)
    import_trending_series(40)
    import_trending_games(20)
    print("Clean import complete!")
