"""
Fills in cast/crew for series and anime, and trailers for games, that were
imported before the importer saved credits. Run from the project root:
    python -m scripts.backfill_series_credits
"""
import os

import requests
from dotenv import load_dotenv

from database import get_db
from services.importer import ensure_person, tmdb_get

load_dotenv()

def fix_series_cast(conn):
    # Find all series / anime
    rows = conn.run(
        "SELECT m.mediaid, m.title FROM media m WHERE m.mediatype IN ('series', 'anime');"
    )
    for row in rows:
        mediaid, title = row[0], row[1]
        print(f"Fixing series cast for: {title}")
        
        # media rows don't keep the TMDB id, so look the show up by title
        res = tmdb_get("search/tv", {"query": title})
        if res.get("results"):
            tmdb_id = res["results"][0]["id"]
            
            credits = tmdb_get(f"tv/{tmdb_id}/credits")
            for member in credits.get("cast", [])[:10]:
                pid = ensure_person(conn, member)
                if not conn.run("SELECT 1 FROM actor WHERE actorid=:id;", id=pid):
                    conn.run("INSERT INTO actor (actorid) VALUES (:id);", id=pid)
                conn.run(
                    "INSERT INTO cast_member (mediaid, actorid, rolename, billingorder) VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;",
                    m=mediaid, a=pid, r=member.get("character", ""), b=member.get("order", 0) + 1)

            for crew in credits.get("crew", []):
                if crew.get("job") == "Executive Producer" or crew.get("job") == "Director":
                    pid = ensure_person(conn, crew)
                    if not conn.run("SELECT 1 FROM director WHERE directorid=:id;", id=pid):
                        conn.run("INSERT INTO director (directorid) VALUES (:id);", id=pid)
                    conn.run(
                        "INSERT INTO media_director (mediaid, directorid) VALUES (:m, :d) ON CONFLICT DO NOTHING;",
                        m=mediaid, d=pid)
        else:
            print(f"Could not find TMDB ID for {title}")

def fix_game_trailers(conn):
    # Find all games
    rows = conn.run("SELECT m.mediaid, m.title FROM media m WHERE m.mediatype = 'game';")
    for row in rows:
        mediaid, title = row[0], row[1]
        print(f"Fixing game trailers for: {title}")
        
        res = requests.get("https://api.rawg.io/api/games", params={"key": os.getenv("RAWG_KEY"), "search": title})
        data = res.json()
        if data.get("results"):
            rawg_id = data["results"][0]["id"]
            
            movie_res = requests.get(f"https://api.rawg.io/api/games/{rawg_id}/movies", params={"key": os.getenv("RAWG_KEY")})
            movie_data = movie_res.json()
            trailernum = 1
            for video in movie_data.get("results", []):
                url = video.get("data", {}).get("max") or video.get("data", {}).get("480")
                if url:
                    existing = conn.run(
                        "SELECT 1 FROM trailer WHERE mediaid=:m AND trailernum=:n;",
                        m=mediaid, n=trailernum)
                    if not existing:
                        conn.run(
                            "INSERT INTO trailer (mediaid, trailernum, title, url) VALUES (:m, :n, :t, :u);",
                            m=mediaid, n=trailernum,
                            t=video.get("name", "Game Trailer"),
                            u=url)
                    trailernum += 1
                    if trailernum > 3:  # max 3 trailers
                        break

        else:
            print(f"Could not find RAWG ID for {title}")

if __name__ == "__main__":
    conn = get_db()
    try:
        fix_series_cast(conn)
        fix_game_trailers(conn)
    finally:
        conn.close()
