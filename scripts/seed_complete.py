"""
seed_complete.py — Comprehensive data seeder for YellowUmbrella
Backfills existing records and adds new movies, series, anime, and games
using live TMDB and RAWG API data.
"""

import requests
import pg8000.native
from dotenv import load_dotenv
import os
import time
import sys

# Add parent dir so we can reuse helpers
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

TMDB_BASE   = "https://api.themoviedb.org/3"
RAWG_BASE   = "https://api.rawg.io/api"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
HEADERS     = {
    "Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}",
    "accept": "application/json"
}
RAWG_KEY = os.getenv("RAWG_KEY")


def get_db():
    return pg8000.native.Connection(
        database=os.getenv("DB_NAME", "imdb_project"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432))
    )


def tmdb_get(path, params={}):
    res = requests.get(f"{TMDB_BASE}/{path}", headers=HEADERS, params=params)
    res.raise_for_status()
    return res.json()


def rawg_get(path, params={}):
    params["key"] = RAWG_KEY
    res = requests.get(f"{RAWG_BASE}/{path}", params=params)
    res.raise_for_status()
    return res.json()


def ensure_genre(conn, name):
    rows = conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)
    if rows:
        return rows[0][0]
    conn.run("INSERT INTO genre (genrename) VALUES (:n);", n=name)
    return conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)[0][0]


def ensure_person(conn, name, photourl=None):
    rows = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)
    if rows:
        pid = rows[0][0]
        if photourl:
            conn.run(
                "UPDATE person SET photourl = :u WHERE personid = :id AND (photourl IS NULL OR photourl = 'None');",
                u=photourl, id=pid
            )
        return pid
    conn.run("INSERT INTO person (name, photourl) VALUES (:n, :u);", n=name, u=photourl)
    return conn.run("SELECT personid FROM person WHERE name=:n;", n=name)[0][0]


def save_trailers(conn, mediaid, tmdb_id, media_type="movie"):
    try:
        endpoint = f"movie/{tmdb_id}/videos" if media_type == "movie" else f"tv/{tmdb_id}/videos"
        data = tmdb_get(endpoint)
        trailernum = 1
        for video in data.get("results", []):
            if video.get("site") == "YouTube" and video.get("type") == "Trailer":
                youtube_url = f"https://www.youtube.com/embed/{video['key']}"
                existing = conn.run(
                    "SELECT 1 FROM trailer WHERE mediaid=:m AND trailernum=:n;",
                    m=mediaid, n=trailernum
                )
                if not existing:
                    conn.run(
                        "INSERT INTO trailer (mediaid, trailernum, title, url) VALUES (:m, :n, :t, :u);",
                        m=mediaid, n=trailernum,
                        t=video.get("name", "Official Trailer"),
                        u=youtube_url
                    )
                trailernum += 1
                if trailernum > 3:
                    break
    except Exception as e:
        print(f"  [trailer warning] {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 1: Backfill existing media poster URLs
# ════════════════════════════════════════════════════════════════
def backfill_existing_media(conn):
    print("\n═══ PHASE 1: Backfilling existing media posters & ratings ═══")

    rows = conn.run("SELECT mediaid, title, mediatype FROM media WHERE posterurl IS NULL OR posterurl = 'None';")
    print(f"  Found {len(rows)} media entries with missing posters")

    # Map titles to TMDB search type
    # We know from seed.sql: IDs 1-5 are movies, 6-8 are series
    title_type_map = {
        "La La Land": "movie",
        "Blade Runner 2049": "movie",
        "Drive": "movie",
        "Past Lives": "movie",
        "Baby Driver": "movie",
        "Beef": "tv",
        "True Detective": "tv",
        "Arcane": "tv",
    }

    for row in rows:
        mediaid, title, _ = row
        search_type = title_type_map.get(title, "movie")

        try:
            if search_type == "movie":
                results = tmdb_get("search/movie", {"query": title}).get("results", [])
            else:
                results = tmdb_get("search/tv", {"query": title}).get("results", [])

            if results:
                item = results[0]
                poster_path = item.get("poster_path")
                posterurl = f"{POSTER_BASE}{poster_path}" if poster_path else None
                rating = item.get("vote_average")

                if posterurl:
                    conn.run("UPDATE media SET posterurl = :p WHERE mediaid = :id;", p=posterurl, id=mediaid)
                    print(f"  ✓ Updated poster for '{title}'")

                if rating:
                    conn.run("UPDATE media SET tmdb_rating = :r WHERE mediaid = :id;", id=mediaid, r=rating)

                # Fix mediatype for series entries
                if search_type == "tv":
                    conn.run("UPDATE media SET mediatype = 'series' WHERE mediaid = :id;", id=mediaid)

                # Fetch trailers
                tmdb_id = item.get("id")
                save_trailers(conn, mediaid, tmdb_id, media_type=search_type)

            time.sleep(0.3)
        except Exception as e:
            print(f"  ✗ Error updating '{title}': {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 2: Backfill person photo URLs
# ════════════════════════════════════════════════════════════════
def backfill_person_photos(conn):
    print("\n═══ PHASE 2: Backfilling person photo URLs ═══")

    rows = conn.run("SELECT personid, name FROM person WHERE photourl IS NULL OR photourl = 'None';")
    print(f"  Found {len(rows)} persons with missing photos")

    for row in rows:
        personid, name = row
        try:
            results = tmdb_get("search/person", {"query": name}).get("results", [])
            if results:
                profile_path = results[0].get("profile_path")
                if profile_path:
                    photourl = f"{POSTER_BASE}{profile_path}"
                    conn.run("UPDATE person SET photourl = :u WHERE personid = :id;", u=photourl, id=personid)
                    print(f"  ✓ Updated photo for '{name}'")
                else:
                    print(f"  ⚠ No photo found for '{name}'")
            time.sleep(0.3)
        except Exception as e:
            print(f"  ✗ Error updating '{name}': {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 3: Add new movies
# ════════════════════════════════════════════════════════════════
def add_movies(conn):
    print("\n═══ PHASE 3: Adding new movies ═══")

    # Popular movie TMDB IDs
    movie_tmdb_ids = [
        550,    # Fight Club
        680,    # Pulp Fiction
        278,    # The Shawshank Redemption
        238,    # The Godfather
        155,    # The Dark Knight
        13,     # Forrest Gump
        120,    # The Lord of the Rings: Fellowship
        157336, # Interstellar
        27205,  # Inception
        244786, # Whiplash
        372058, # Your Name
        497,    # The Green Mile
        389,    # 12 Angry Men
        11,     # Star Wars: A New Hope
        569094, # Spider-Man: Across the Spider-Verse
        786892, # Furiosa
        445117, # Top Gun: Maverick
        823464, # Godzilla x Kong
        693134, # Dune: Part Two
        940721, # Godzilla Minus One
    ]

    for tmdb_id in movie_tmdb_ids:
        try:
            data = tmdb_get(f"movie/{tmdb_id}")
            credits = tmdb_get(f"movie/{tmdb_id}/credits")
            title = data.get("title", "Unknown")

            # Skip if already exists
            existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
            if existing:
                print(f"  ⊘ Already exists: '{title}'")
                # Still update poster if missing
                mid = existing[0][0]
                poster_check = conn.run("SELECT posterurl FROM media WHERE mediaid=:id;", id=mid)
                if poster_check and (poster_check[0][0] is None or poster_check[0][0] == 'None'):
                    poster_path = data.get("poster_path")
                    if poster_path:
                        conn.run("UPDATE media SET posterurl=:p WHERE mediaid=:id;",
                                 p=f"{POSTER_BASE}{poster_path}", id=mid)
                continue

            releasedate = data.get("release_date") or None
            poster_path = data.get("poster_path")
            posterurl = f"{POSTER_BASE}{poster_path}" if poster_path else None
            avgrating = data.get("vote_average") or None
            durationmin = data.get("runtime") or None
            boxoffice = data.get("revenue") or None
            if boxoffice == 0:
                boxoffice = None

            conn.run(
                "INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'movie');",
                t=title, r=releasedate, p=posterurl, a=avgrating
            )
            mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
            conn.run(
                "INSERT INTO movie (movieid, durationmin, boxoffice) VALUES (:id, :d, :b);",
                id=mediaid, d=durationmin, b=boxoffice
            )

            # Genres
            for g in data.get("genres", []):
                gid = ensure_genre(conn, g["name"])
                conn.run(
                    "INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                    m=mediaid, g=gid
                )

            # Cast (top 8)
            for member in credits.get("cast", [])[:8]:
                profile_path = member.get("profile_path")
                photourl = f"{POSTER_BASE}{profile_path}" if profile_path else None
                pid = ensure_person(conn, member["name"], photourl)
                if not conn.run("SELECT 1 FROM actor WHERE actorid=:id;", id=pid):
                    conn.run("INSERT INTO actor (actorid) VALUES (:id);", id=pid)
                conn.run(
                    "INSERT INTO cast_member (mediaid, actorid, rolename, billingorder) VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;",
                    m=mediaid, a=pid, r=member.get("character", ""), b=member.get("order", 0) + 1
                )

            # Directors
            for crew in credits.get("crew", []):
                if crew.get("job") == "Director":
                    profile_path = crew.get("profile_path")
                    photourl = f"{POSTER_BASE}{profile_path}" if profile_path else None
                    pid = ensure_person(conn, crew["name"], photourl)
                    if not conn.run("SELECT 1 FROM director WHERE directorid=:id;", id=pid):
                        conn.run("INSERT INTO director (directorid) VALUES (:id);", id=pid)
                    conn.run(
                        "INSERT INTO media_director (mediaid, directorid) VALUES (:m, :d) ON CONFLICT DO NOTHING;",
                        m=mediaid, d=pid
                    )

            # Trailers
            save_trailers(conn, mediaid, tmdb_id, media_type="movie")

            print(f"  ✓ Added movie: '{title}' (poster: {'yes' if posterurl else 'no'})")
            time.sleep(0.3)

        except Exception as e:
            print(f"  ✗ Error adding movie TMDB#{tmdb_id}: {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 4: Add new series
# ════════════════════════════════════════════════════════════════
def add_series(conn):
    print("\n═══ PHASE 4: Adding new series ═══")

    series_tmdb_ids = [
        1396,   # Breaking Bad
        1399,   # Game of Thrones
        66732,  # Stranger Things
        82856,  # The Mandalorian
        94997,  # House of the Dragon
        76479,  # The Boys
        60735,  # The Flash
        71446,  # Money Heist
        93405,  # Squid Game
        84958,  # Loki
        100088, # The Last of Us
        114472, # Wednesday
        136315, # The Bear
        95396,  # Severance
    ]

    for tmdb_id in series_tmdb_ids:
        try:
            data = tmdb_get(f"tv/{tmdb_id}")
            title = data.get("name", "Unknown")

            existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
            if existing:
                print(f"  ⊘ Already exists: '{title}'")
                mid = existing[0][0]
                poster_check = conn.run("SELECT posterurl FROM media WHERE mediaid=:id;", id=mid)
                if poster_check and (poster_check[0][0] is None or poster_check[0][0] == 'None'):
                    poster_path = data.get("poster_path")
                    if poster_path:
                        conn.run("UPDATE media SET posterurl=:p WHERE mediaid=:id;",
                                 p=f"{POSTER_BASE}{poster_path}", id=mid)
                continue

            releasedate = data.get("first_air_date") or None
            poster_path = data.get("poster_path")
            posterurl = f"{POSTER_BASE}{poster_path}" if poster_path else None
            avgrating = data.get("vote_average") or None
            totalseasons = data.get("number_of_seasons") or None
            tmdb_status = data.get("status", "")
            status = ("Ongoing" if tmdb_status == "Returning Series" else
                      "Ended" if tmdb_status == "Ended" else
                      "Canceled" if tmdb_status == "Canceled" else None)

            conn.run(
                "INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'series');",
                t=title, r=releasedate, p=posterurl, a=avgrating
            )
            mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
            conn.run(
                "INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st);",
                id=mediaid, ts=totalseasons, st=status
            )

            # Genres
            for g in data.get("genres", []):
                gid = ensure_genre(conn, g["name"])
                conn.run(
                    "INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                    m=mediaid, g=gid
                )

            # Fetch credits for cast
            try:
                credits = tmdb_get(f"tv/{tmdb_id}/credits")
                for member in credits.get("cast", [])[:8]:
                    profile_path = member.get("profile_path")
                    photourl = f"{POSTER_BASE}{profile_path}" if profile_path else None
                    pid = ensure_person(conn, member["name"], photourl)
                    if not conn.run("SELECT 1 FROM actor WHERE actorid=:id;", id=pid):
                        conn.run("INSERT INTO actor (actorid) VALUES (:id);", id=pid)
                    conn.run(
                        "INSERT INTO cast_member (mediaid, actorid, rolename, billingorder) VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;",
                        m=mediaid, a=pid, r=member.get("character", ""), b=member.get("order", 0) + 1
                    )
            except Exception as e:
                print(f"    [cast warning] {e}")

            # Trailers
            save_trailers(conn, mediaid, tmdb_id, media_type="tv")

            print(f"  ✓ Added series: '{title}' (poster: {'yes' if posterurl else 'no'})")
            time.sleep(0.3)

        except Exception as e:
            print(f"  ✗ Error adding series TMDB#{tmdb_id}: {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 5: Add anime
# ════════════════════════════════════════════════════════════════
def add_anime(conn):
    print("\n═══ PHASE 5: Adding anime ═══")

    # Popular anime TMDB IDs (TV shows)
    anime_tmdb_ids = [
        1429,    # Attack on Titan
        85937,   # Demon Slayer
        46260,   # Naruto
        31911,   # One Piece (anime)
        37854,   # One Punch Man
        65930,   # My Hero Academia
        63926,   # One Piece
        60863,   # Death Note
        12971,   # Dragon Ball Z
        64196,   # Hunter x Hunter (2011)
        72636,   # Mob Psycho 100
        95557,   # Jujutsu Kaisen
        114410,  # Chainsaw Man
        44006,   # Fullmetal Alchemist: Brotherhood
        62104,   # Neon Genesis Evangelion
        127532,  # Solo Leveling
    ]

    for tmdb_id in anime_tmdb_ids:
        try:
            data = tmdb_get(f"tv/{tmdb_id}")
            title = data.get("name", "Unknown")

            existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
            if existing:
                print(f"  ⊘ Already exists: '{title}'")
                mid = existing[0][0]
                # Update poster if missing
                poster_check = conn.run("SELECT posterurl FROM media WHERE mediaid=:id;", id=mid)
                if poster_check and (poster_check[0][0] is None or poster_check[0][0] == 'None'):
                    poster_path = data.get("poster_path")
                    if poster_path:
                        conn.run("UPDATE media SET posterurl=:p WHERE mediaid=:id;",
                                 p=f"{POSTER_BASE}{poster_path}", id=mid)
                # Also check if it's in the anime table
                anime_check = conn.run("SELECT 1 FROM anime WHERE animeid=:id;", id=mid)
                if not anime_check:
                    # Need to add to anime table and also series table if needed
                    series_check = conn.run("SELECT 1 FROM series WHERE seriesid=:id;", id=mid)
                    if not series_check:
                        totalseasons = data.get("number_of_seasons") or 1
                        status_raw = data.get("status", "")
                        status = ("Ongoing" if status_raw == "Returning Series" else
                                  "Ended" if status_raw == "Ended" else None)
                        conn.run("INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st);",
                                 id=mid, ts=totalseasons, st=status)
                    studio = data.get("production_companies", [{}])[0].get("name") if data.get("production_companies") else None
                    conn.run(
                        "INSERT INTO anime (animeid, totalseasons, totalepisodes, studio_name, status) VALUES (:id, :ts, :te, :sn, :st);",
                        id=mid, ts=data.get("number_of_seasons"),
                        te=data.get("number_of_episodes"),
                        sn=studio,
                        st=("Ongoing" if data.get("status") == "Returning Series" else "Ended" if data.get("status") == "Ended" else None)
                    )
                    conn.run("UPDATE media SET mediatype='anime' WHERE mediaid=:id;", id=mid)
                    print(f"    → Also added to anime table")
                continue

            releasedate = data.get("first_air_date") or None
            poster_path = data.get("poster_path")
            posterurl = f"{POSTER_BASE}{poster_path}" if poster_path else None
            avgrating = data.get("vote_average") or None
            totalseasons = data.get("number_of_seasons") or None
            totalepisodes = data.get("number_of_episodes") or None
            studio = data.get("production_companies", [{}])[0].get("name") if data.get("production_companies") else None

            tmdb_status = data.get("status", "")
            status = ("Ongoing" if tmdb_status == "Returning Series" else
                      "Ended" if tmdb_status == "Ended" else
                      "Canceled" if tmdb_status == "Canceled" else None)

            conn.run(
                "INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'anime');",
                t=title, r=releasedate, p=posterurl, a=avgrating
            )
            mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]

            # Anime needs to also be in the series table (ISA hierarchy)
            conn.run(
                "INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st);",
                id=mediaid, ts=totalseasons, st=status
            )
            conn.run(
                "INSERT INTO anime (animeid, totalseasons, totalepisodes, studio_name, status) VALUES (:id, :ts, :te, :sn, :st);",
                id=mediaid, ts=totalseasons, te=totalepisodes, sn=studio, st=status
            )

            # Genres
            for g in data.get("genres", []):
                gid = ensure_genre(conn, g["name"])
                conn.run(
                    "INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                    m=mediaid, g=gid
                )

            # Fetch credits for cast
            try:
                credits = tmdb_get(f"tv/{tmdb_id}/credits")
                for member in credits.get("cast", [])[:6]:
                    profile_path = member.get("profile_path")
                    photourl = f"{POSTER_BASE}{profile_path}" if profile_path else None
                    pid = ensure_person(conn, member["name"], photourl)
                    if not conn.run("SELECT 1 FROM actor WHERE actorid=:id;", id=pid):
                        conn.run("INSERT INTO actor (actorid) VALUES (:id);", id=pid)
                    conn.run(
                        "INSERT INTO cast_member (mediaid, actorid, rolename, billingorder) VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;",
                        m=mediaid, a=pid, r=member.get("character", ""), b=member.get("order", 0) + 1
                    )
            except Exception as e:
                print(f"    [cast warning] {e}")

            # Trailers
            save_trailers(conn, mediaid, tmdb_id, media_type="tv")

            print(f"  ✓ Added anime: '{title}' (poster: {'yes' if posterurl else 'no'})")
            time.sleep(0.3)

        except Exception as e:
            print(f"  ✗ Error adding anime TMDB#{tmdb_id}: {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 6: Add games
# ════════════════════════════════════════════════════════════════
def add_games(conn):
    print("\n═══ PHASE 6: Adding games ═══")

    # Popular game RAWG IDs
    game_rawg_ids = [
        3498,   # Grand Theft Auto V
        3328,   # The Witcher 3: Wild Hunt
        4200,   # Portal 2
        5286,   # Tomb Raider (2013)
        4291,   # Counter-Strike: Global Offensive
        12020,  # Left 4 Dead 2
        5679,   # The Elder Scrolls V: Skyrim
        28,     # Red Dead Redemption 2
        802,    # Borderlands 2
        13536,  # Portal
        58175,  # God of War (2018)
        32,     # Destiny 2
        326243, # Elden Ring
        793,    # Cyberpunk 2077
        324997, # Baldur's Gate 3
    ]

    for rawg_id in game_rawg_ids:
        try:
            data = rawg_get(f"games/{rawg_id}")
            title = data.get("name", "Unknown")

            existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
            if existing:
                print(f"  ⊘ Already exists: '{title}'")
                mid = existing[0][0]
                # Update poster if missing
                poster_check = conn.run("SELECT posterurl FROM media WHERE mediaid=:id;", id=mid)
                if poster_check and (poster_check[0][0] is None or poster_check[0][0] == 'None'):
                    bg_image = data.get("background_image")
                    if bg_image:
                        conn.run("UPDATE media SET posterurl=:p WHERE mediaid=:id;",
                                 p=bg_image, id=mid)
                continue

            releasedate = data.get("released") or None
            posterurl = data.get("background_image") or None
            avgrating = data.get("rating") or None

            # Scale RAWG's 5-point rating to 10-point
            if avgrating:
                avgrating = round(avgrating * 2, 1)

            platforms = ", ".join([p["platform"]["name"] for p in data.get("platforms", [])[:5]])
            developer = data.get("developers", [{}])[0].get("name") if data.get("developers") else None
            publisher = data.get("publishers", [{}])[0].get("name") if data.get("publishers") else None
            esrb = data.get("esrb_rating", {})
            esrb_rating = esrb.get("name") if esrb else None

            conn.run(
                "INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'game');",
                t=title, r=releasedate, p=posterurl, a=avgrating
            )
            mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
            conn.run(
                "INSERT INTO game (gameid, developer, publisher, platform, esrb_rating) VALUES (:id, :dev, :pub, :pl, :e);",
                id=mediaid, dev=developer, pub=publisher, pl=platforms, e=esrb_rating
            )

            # Genres
            for g in data.get("genres", []):
                gid = ensure_genre(conn, g["name"])
                conn.run(
                    "INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                    m=mediaid, g=gid
                )

            print(f"  ✓ Added game: '{title}' (poster: {'yes' if posterurl else 'no'})")
            time.sleep(0.5)

        except Exception as e:
            print(f"  ✗ Error adding game RAWG#{rawg_id}: {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 7: Add missing reviews for entries without ratings
# ════════════════════════════════════════════════════════════════
def add_missing_reviews(conn):
    print("\n═══ PHASE 7: Adding reviews for entries missing ratings ═══")

    # Find entries where avgrating is NULL but we have a tmdb/rawg rating
    rows = conn.run("""
        SELECT mediaid, title, avgrating FROM media
        WHERE avgrating IS NULL OR avgrating = 0;
    """)
    print(f"  Found {len(rows)} entries with missing ratings")

    # We'll create a dummy user for seeding reviews if needed
    user_rows = conn.run("SELECT userid FROM users LIMIT 1;")
    if not user_rows:
        print("  No users found, skipping reviews")
        return

    userid = user_rows[0][0]

    for row in rows:
        mediaid, title, _ = row
        # Check if we have a tmdb_rating from the backfill
        tmdb_rows = conn.run("SELECT tmdb_rating FROM media WHERE mediaid=:id;", id=mediaid)
        try:
            if tmdb_rows and tmdb_rows[0][0]:
                rating = min(10, max(1, int(float(tmdb_rows[0][0]))))
                # Check if review already exists
                existing = conn.run(
                    "SELECT 1 FROM review WHERE mediaid=:m AND userid=:u;",
                    m=mediaid, u=userid
                )
                if not existing:
                    conn.run(
                        "INSERT INTO review (mediaid, userid, rating, commenttext, reviewdate) VALUES (:m, :u, :r, :c, CURRENT_DATE);",
                        m=mediaid, u=userid, r=rating, c=f"Great {title}!"
                    )
                    print(f"  ✓ Added review for '{title}' (rating: {rating})")
        except Exception as e:
            print(f"  ✗ Error adding review for '{title}': {e}")


# ════════════════════════════════════════════════════════════════
# PHASE 8: Final cleanup - ensure all entries have proper data
# ════════════════════════════════════════════════════════════════
def final_cleanup(conn):
    print("\n═══ PHASE 8: Final cleanup ═══")

    # Remove any "Trending Anime X" or "Trending Game X" placeholder entries
    conn.run("DELETE FROM anime WHERE animeid IN (SELECT mediaid FROM media WHERE title LIKE 'Trending Anime %');")
    conn.run("DELETE FROM game WHERE gameid IN (SELECT mediaid FROM media WHERE title LIKE 'Trending Game %');")
    conn.run("DELETE FROM series WHERE seriesid IN (SELECT mediaid FROM media WHERE title LIKE 'Trending Anime %');")
    conn.run("DELETE FROM media WHERE title LIKE 'Trending Anime %' OR title LIKE 'Trending Game %';")
    print("  ✓ Cleaned up placeholder entries")

    # Fix the mediatype for Beef, True Detective, Arcane
    conn.run("UPDATE media SET mediatype='series' WHERE mediaid IN (6, 7, 8) AND mediatype='movie';")
    print("  ✓ Fixed mediatype for series entries (IDs 6-8)")

    # Print final counts
    counts = {
        "movies": conn.run("SELECT COUNT(*) FROM movie;")[0][0],
        "series": conn.run("SELECT COUNT(*) FROM series s LEFT JOIN anime a ON s.seriesid=a.animeid WHERE a.animeid IS NULL;")[0][0],
        "anime": conn.run("SELECT COUNT(*) FROM anime;")[0][0],
        "games": conn.run("SELECT COUNT(*) FROM game;")[0][0],
    }
    print(f"\n  📊 Final counts:")
    for k, v in counts.items():
        print(f"     {k}: {v}")

    null_posters = conn.run("SELECT COUNT(*) FROM media WHERE posterurl IS NULL OR posterurl = 'None';")[0][0]
    null_photos = conn.run("SELECT COUNT(*) FROM person WHERE photourl IS NULL OR photourl = 'None';")[0][0]
    print(f"     Media with missing posters: {null_posters}")
    print(f"     Persons with missing photos: {null_photos}")


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🎬 YellowUmbrella — Comprehensive Data Seeder")
    print("=" * 60)

    conn = get_db()
    try:
        backfill_existing_media(conn)
        backfill_person_photos(conn)
        add_movies(conn)
        add_series(conn)
        add_anime(conn)
        add_games(conn)
        add_missing_reviews(conn)
        final_cleanup(conn)

        print("\n✅ Seeding complete!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
