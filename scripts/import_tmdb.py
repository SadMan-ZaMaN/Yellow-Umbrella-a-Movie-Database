"""
Bulk-imports popular movies, series and anime from TMDB.
Run from the project root:  python -m scripts.import_tmdb
"""
import requests
import pg8000.native
from dotenv import load_dotenv
import os
import time

load_dotenv()

# ── TMDB setup ──────────────────────────────────────────────
TMDB_BASE = "https://api.themoviedb.org/3"
HEADERS = {
    "Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}",
    "accept": "application/json"
}
POSTER_BASE = "https://image.tmdb.org/t/p/w500"

# ── DB setup ─────────────────────────────────────────────────
def get_db():
    return pg8000.native.Connection(
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT"))
    )

# ── Helpers ──────────────────────────────────────────────────
def tmdb_get(path, params={}):
    url = f"{TMDB_BASE}/{path}"
    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()
    return res.json()

def ensure_genre(conn, name):
    """Insert genre if not exists, return genreid"""
    rows = conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)
    if rows:
        return rows[0][0]
    conn.run("INSERT INTO genre (genrename) VALUES (:n);", n=name)
    rows = conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)
    return rows[0][0]

def ensure_person(conn, tmdb_person):
    """Insert person if not exists, return personid"""
    name = tmdb_person.get("name", "Unknown")
    rows = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)
    if rows:
        return rows[0][0]
    conn.run(
        "INSERT INTO person (name) VALUES (:n);", n=name)
    rows = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)
    return rows[0][0]

# ── Import a single movie by TMDB id ─────────────────────────
def import_movie(conn, tmdb_id):
    # Check if already imported (use tmdb_id stored in posterurl as marker — or just check title)
    data = tmdb_get(f"movie/{tmdb_id}")
    credits = tmdb_get(f"movie/{tmdb_id}/credits")

    title = data.get("title", "Unknown")
    releasedate = data.get("release_date") or None
    posterurl = f"{POSTER_BASE}{data['poster_path']}" if data.get("poster_path") else None
    durationmin = data.get("runtime") or None
    boxoffice = data.get("revenue") or None
    if boxoffice == 0:
        boxoffice = None

    # Check duplicate
    existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
    if existing:
        print(f"  Skipping (already exists): {title}")
        return existing[0][0]

    # Insert into media
    conn.run(
        "INSERT INTO media (title, releasedate, posterurl, mediatype) VALUES (:t, :r, :p, 'movie');",
        t=title, r=releasedate, p=posterurl)
    mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]

    # Insert into movie
    conn.run(
        "INSERT INTO movie (movieid, durationmin, boxoffice) VALUES (:id, :d, :b);",
        id=mediaid, d=durationmin, b=boxoffice)

    # Genres
    for g in data.get("genres", []):
        gid = ensure_genre(conn, g["name"])
        conn.run(
            "INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
            m=mediaid, g=gid)

    # Cast (top 10 only)
    for member in credits.get("cast", [])[:10]:
        pid = ensure_person(conn, member)
        # Make sure they're in actor table
        existing_actor = conn.run("SELECT 1 FROM actor WHERE actorid=:id;", id=pid)
        if not existing_actor:
            conn.run("INSERT INTO actor (actorid) VALUES (:id);", id=pid)
        conn.run(
            """INSERT INTO cast_member (mediaid, actorid, rolename, billingorder)
               VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;""",
            m=mediaid, a=pid,
            r=member.get("character", ""),
            b=member.get("order", 0) + 1)

    # Directors
    for crew in credits.get("crew", []):
        if crew.get("job") == "Director":
            pid = ensure_person(conn, crew)
            existing_dir = conn.run("SELECT 1 FROM director WHERE directorid=:id;", id=pid)
            if not existing_dir:
                conn.run("INSERT INTO director (directorid) VALUES (:id);", id=pid)
            conn.run(
                "INSERT INTO media_director (mediaid, directorid) VALUES (:m, :d) ON CONFLICT DO NOTHING;",
                m=mediaid, d=pid)

    print(f"  ✓ Imported movie: {title} (mediaid={mediaid})")
    return mediaid

# ── Import a TV series by TMDB id ────────────────────────────
def import_series(conn, tmdb_id, mediatype="series"):
    data = tmdb_get(f"tv/{tmdb_id}")
    credits = tmdb_get(f"tv/{tmdb_id}/credits")

    title = data.get("name", "Unknown")
    releasedate = data.get("first_air_date") or None
    posterurl = f"{POSTER_BASE}{data['poster_path']}" if data.get("poster_path") else None
    totalseasons = data.get("number_of_seasons") or None
    tmdb_status = data.get("status", "")
    status = "Ongoing" if tmdb_status == "Returning Series" else \
             "Ended" if tmdb_status == "Ended" else \
             "Canceled" if tmdb_status == "Canceled" else None

    existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
    if existing:
        print(f"  Skipping (already exists): {title}")
        return existing[0][0]

    conn.run(
        "INSERT INTO media (title, releasedate, posterurl, mediatype) VALUES (:t, :r, :p, :mt);",
        t=title, r=releasedate, p=posterurl, mt=mediatype)
    mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]

    if mediatype == "anime":
        # Get anime studio from networks/production
        studio_name = None
        for company in data.get("production_companies", [])[:1]:
            studio_name = company.get("name")
        totalepisodes = data.get("number_of_episodes") or None
        conn.run(
            """INSERT INTO anime (animeid, totalseasons, totalepisodes, studio_name, status)
               VALUES (:id, :ts, :te, :sn, :st);""",
            id=mediaid, ts=totalseasons, te=totalepisodes,
            sn=studio_name, st=status)
    else:
        conn.run(
            "INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st);",
            id=mediaid, ts=totalseasons, st=status)

    # Genres
    for g in data.get("genres", []):
        gid = ensure_genre(conn, g["name"])
        conn.run(
            "INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
            m=mediaid, g=gid)

    print(f"  ✓ Imported {mediatype}: {title} (mediaid={mediaid})")
    return mediaid

# ── Bulk import popular movies ────────────────────────────────
def import_popular_movies(conn, pages=3):
    """Import top popular movies — 20 per page, so pages=3 gives 60 movies"""
    print(f"\nImporting popular movies ({pages} pages)...")
    for page in range(1, pages + 1):
        data = tmdb_get("movie/popular", {"page": page})
        for movie in data.get("results", []):
            try:
                import_movie(conn, movie["id"])
                time.sleep(0.3)   # be polite to the API
            except Exception as e:
                print(f"  ✗ Failed {movie.get('title')}: {e}")

# ── Bulk import popular series ────────────────────────────────
def import_popular_series(conn, pages=2):
    print(f"\nImporting popular series ({pages} pages)...")
    for page in range(1, pages + 1):
        data = tmdb_get("tv/popular", {"page": page})
        for show in data.get("results", []):
            try:
                import_series(conn, show["id"], mediatype="series")
                time.sleep(0.3)
            except Exception as e:
                print(f"  ✗ Failed {show.get('name')}: {e}")

# ── Import anime (TMDB marks anime as Animation + origin Japan) ──
def import_popular_anime(conn, pages=2):
    print(f"\nImporting popular anime ({pages} pages)...")
    for page in range(1, pages + 1):
        # Filter: animation genre (id=16) + Japanese origin
        data = tmdb_get("discover/tv", {
            "with_genres": "16",
            "with_origin_country": "JP",
            "page": page
        })
        for show in data.get("results", []):
            try:
                import_series(conn, show["id"], mediatype="anime")
                time.sleep(0.3)
            except Exception as e:
                print(f"  ✗ Failed {show.get('name')}: {e}")

# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    conn = get_db()
    try:
        import_popular_movies(conn, pages=3)    # ~60 movies
        import_popular_series(conn, pages=2)    # ~40 series
        import_popular_anime(conn, pages=2)     # ~40 anime
        print("\n✅ Import complete!")
    finally:
        conn.close()
