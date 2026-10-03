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
POSTER_BASE = "https://image.tmdb.org/t/p/w500"

# ── DB ───────────────────────────────────────────────────────
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

# ── Helpers (same as import_tmdb.py) ────────────────────────
def ensure_genre(conn, name):
    rows = conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)
    if rows:
        return rows[0][0]
    conn.run("INSERT INTO genre (genrename) VALUES (:n);", n=name)
    return conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)[0][0]

def ensure_person(conn, tmdb_person):
    name = tmdb_person.get("name", "Unknown")
    rows = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)
    if rows:
        return rows[0][0]
    conn.run("INSERT INTO person (name) VALUES (:n);", n=name)
    return conn.run("SELECT personid FROM person WHERE name=:n;", n=name)[0][0]

# ── Import functions ─────────────────────────────────────────
def import_movie(conn, tmdb_id):
    data     = tmdb_get(f"movie/{tmdb_id}")
    credits  = tmdb_get(f"movie/{tmdb_id}/credits")
    title    = data.get("title", "Unknown")

    existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
    if existing:
        print(f"  '{title}' already in database (mediaid={existing[0][0]})")
        return

    releasedate = data.get("release_date") or None
    posterurl   = f"{POSTER_BASE}{data['poster_path']}" if data.get("poster_path") else None
    durationmin = data.get("runtime") or None
    boxoffice   = data.get("revenue") or None
    if boxoffice == 0:
        boxoffice = None

    conn.run(
        "INSERT INTO media (title, releasedate, posterurl, mediatype) VALUES (:t, :r, :p, 'movie');",
        t=title, r=releasedate, p=posterurl)
    mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
    conn.run(
        "INSERT INTO movie (movieid, durationmin, boxoffice) VALUES (:id, :d, :b);",
        id=mediaid, d=durationmin, b=boxoffice)

    for g in data.get("genres", []):
        gid = ensure_genre(conn, g["name"])
        conn.run("INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                 m=mediaid, g=gid)

    for member in credits.get("cast", [])[:10]:
        pid = ensure_person(conn, member)
        if not conn.run("SELECT 1 FROM actor WHERE actorid=:id;", id=pid):
            conn.run("INSERT INTO actor (actorid) VALUES (:id);", id=pid)
        conn.run(
            """INSERT INTO cast_member (mediaid, actorid, rolename, billingorder)
               VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;""",
            m=mediaid, a=pid,
            r=member.get("character", ""),
            b=member.get("order", 0) + 1)

    for crew in credits.get("crew", []):
        if crew.get("job") == "Director":
            pid = ensure_person(conn, crew)
            if not conn.run("SELECT 1 FROM director WHERE directorid=:id;", id=pid):
                conn.run("INSERT INTO director (directorid) VALUES (:id);", id=pid)
            conn.run(
                "INSERT INTO media_director (mediaid, directorid) VALUES (:m, :d) ON CONFLICT DO NOTHING;",
                m=mediaid, d=pid)

    print(f"  ✓ Imported movie: {title} (mediaid={mediaid})")


def import_series(conn, tmdb_id, mediatype="series"):
    data   = tmdb_get(f"tv/{tmdb_id}")
    title  = data.get("name", "Unknown")

    existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
    if existing:
        print(f"  '{title}' already in database (mediaid={existing[0][0]})")
        return

    releasedate  = data.get("first_air_date") or None
    posterurl    = f"{POSTER_BASE}{data['poster_path']}" if data.get("poster_path") else None
    totalseasons = data.get("number_of_seasons") or None
    tmdb_status  = data.get("status", "")
    status = ("Ongoing"  if tmdb_status == "Returning Series" else
              "Ended"    if tmdb_status == "Ended"            else
              "Canceled" if tmdb_status == "Canceled"         else None)

    conn.run(
        "INSERT INTO media (title, releasedate, posterurl, mediatype) VALUES (:t, :r, :p, :mt);",
        t=title, r=releasedate, p=posterurl, mt=mediatype)
    mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]

    if mediatype == "anime":
        studio_name   = data.get("production_companies", [{}])[0].get("name") if data.get("production_companies") else None
        totalepisodes = data.get("number_of_episodes") or None
        conn.run(
            "INSERT INTO anime (animeid, totalseasons, totalepisodes, studio_name, status) VALUES (:id, :ts, :te, :sn, :st);",
            id=mediaid, ts=totalseasons, te=totalepisodes, sn=studio_name, st=status)
    else:
        conn.run(
            "INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st);",
            id=mediaid, ts=totalseasons, st=status)

    for g in data.get("genres", []):
        gid = ensure_genre(conn, g["name"])
        conn.run("INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                 m=mediaid, g=gid)

    print(f"  ✓ Imported {mediatype}: {title} (mediaid={mediaid})")


# ── Search TMDB and show results for user to pick ────────────
def search_and_pick(query, media_type):
    """
    Search TMDB, show numbered results, let user pick one.
    media_type: 'movie', 'series', or 'anime'
    """
    endpoint = "search/movie" if media_type == "movie" else "search/tv"
    data     = tmdb_get(endpoint, {"query": query})
    results  = data.get("results", [])

    if not results:
        print(f"\n  No results found for '{query}'")
        return None

    print(f"\n  Results for '{query}':\n")
    for i, r in enumerate(results[:8]):
        title = r.get("title") or r.get("name", "Unknown")
        year  = (r.get("release_date") or r.get("first_air_date") or "????")[:4]
        print(f"  [{i+1}]  {title}  ({year})")

    print(f"  [0]  Cancel\n")

    while True:
        try:
            choice = int(input("  Pick a number: "))
            if choice == 0:
                return None
            if 1 <= choice <= len(results[:8]):
                return results[choice - 1]["id"]
            print("  Invalid number, try again.")
        except ValueError:
            print("  Please enter a number.")


# ── Main interactive loop ────────────────────────────────────
def main():
    conn = get_db()
    print("\n╔══════════════════════════════════╗")
    print("║   IMDB Project — Import by Name  ║")
    print("╚══════════════════════════════════╝")

    while True:
        print("\nWhat do you want to import?")
        print("  [1] Movie")
        print("  [2] Series")
        print("  [3] Anime")
        print("  [0] Exit\n")

        choice = input("  Choose type: ").strip()

        if choice == "0":
            print("\n  Bye!\n")
            break

        if choice not in ("1", "2", "3"):
            print("  Invalid choice.")
            continue

        media_type = {"1": "movie", "2": "series", "3": "anime"}[choice]
        query      = input(f"\n  Enter {media_type} name: ").strip()

        if not query:
            print("  Name cannot be empty.")
            continue

        tmdb_id = search_and_pick(query, media_type)

        if tmdb_id is None:
            print("  Cancelled.")
            continue

        print()
        try:
            if media_type == "movie":
                import_movie(conn, tmdb_id)
            else:
                import_series(conn, tmdb_id, mediatype=media_type)
        except Exception as e:
            print(f"  ✗ Error: {e}")

        # Ask if they want to import another
        again = input("\n  Import another? (y/n): ").strip().lower()
        if again != "y":
            print("\n  Done!\n")
            break

    conn.close()


if __name__ == "__main__":
    main()