"""
Re-fetches cast, directors, box office and trailers for every movie already
in the database. Run from the project root:  python -m scripts.backfill_movie_credits
"""
from database import get_db
from services.importer import ensure_person, fetch_and_save_trailers, tmdb_get

def fix_movie_metadata(conn):
    # Find all movies
    rows = conn.run(
        "SELECT m.mediaid, m.title FROM media m JOIN movie mo ON m.mediaid = mo.movieid;"
    )
    for row in rows:
        mediaid, title = row[0], row[1]
        print(f"Fixing movie metadata for: {title}")
        
        # Search TMDB for movie
        res = tmdb_get("search/movie", {"query": title})
        if res.get("results"):
            tmdb_id = res["results"][0]["id"]
            
            # Fetch full movie data
            try:
                data = tmdb_get(f"movie/{tmdb_id}")
                credits = tmdb_get(f"movie/{tmdb_id}/credits")
            except Exception as e:
                print(f"Failed to fetch data for {title}: {e}")
                continue
            
            # Update Box Office if missing
            boxoffice = data.get("revenue") or None
            duration = data.get("runtime") or None
            if boxoffice == 0:
                boxoffice = None
            
            conn.run(
                "UPDATE movie SET boxoffice = :b, durationmin = COALESCE(durationmin, :d) WHERE movieid = :id AND boxoffice IS NULL;",
                b=boxoffice, d=duration, id=mediaid)

            # Insert Cast
            for member in credits.get("cast", [])[:10]:
                pid = ensure_person(conn, member)
                if not conn.run("SELECT 1 FROM actor WHERE actorid=:id;", id=pid):
                    conn.run("INSERT INTO actor (actorid) VALUES (:id);", id=pid)
                conn.run(
                    "INSERT INTO cast_member (mediaid, actorid, rolename, billingorder) VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;",
                    m=mediaid, a=pid, r=member.get("character", ""), b=member.get("order", 0) + 1)

            # Insert Crew (Directors)
            for crew in credits.get("crew", []):
                if crew.get("job") == "Director":
                    pid = ensure_person(conn, crew)
                    if not conn.run("SELECT 1 FROM director WHERE directorid=:id;", id=pid):
                        conn.run("INSERT INTO director (directorid) VALUES (:id);", id=pid)
                    conn.run(
                        "INSERT INTO media_director (mediaid, directorid) VALUES (:m, :d) ON CONFLICT DO NOTHING;",
                        m=mediaid, d=pid)
            
            # Fetch Trailers
            fetch_and_save_trailers(conn, mediaid, tmdb_id, media_type="movie")
            
        else:
            print(f"Could not find TMDB ID for {title}")

if __name__ == "__main__":
    conn = get_db()
    try:
        fix_movie_metadata(conn)
    finally:
        conn.close()
