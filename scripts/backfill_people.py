import requests
import pg8000.native
from dotenv import load_dotenv
import os
import time

load_dotenv()

TMDB_BASE   = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
HEADERS     = {
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

def backfill_people(conn):
    # get all people with missing photo or birthdate
    people = conn.run("""
        SELECT personid, name FROM person
        WHERE photourl IS NULL OR birthdate IS NULL
        ORDER BY name;
    """)
    print(f"Found {len(people)} people with missing info\n")

    for person in people:
        personid, name = person[0], person[1]
        try:
            # search TMDB by name
            search = tmdb_get("search/person", {"query": name})
            results = search.get("results", [])
            if not results:
                print(f"  ✗ Not found: {name}")
                continue

            # get full details using TMDB person id
            tmdb_id  = results[0]["id"]
            data     = tmdb_get(f"person/{tmdb_id}")

            bio      = data.get("biography") or None
            photourl = f"{POSTER_BASE}{data['profile_path']}" \
                       if data.get("profile_path") else None
            birthday = data.get("birthday") or None

            conn.run("BEGIN")
            conn.run("""
                UPDATE person
                SET bio=:b, photourl=:p, birthdate=:bd
                WHERE personid=:id;
            """, b=bio, p=photourl, bd=birthday, id=personid)
            conn.run("COMMIT")

            print(f"  ✓ Updated: {name}")
            time.sleep(0.3)

        except Exception as e:
            conn.run("ROLLBACK")
            print(f"  ✗ Error for {name}: {e}")

if __name__ == "__main__":
    conn = get_db()
    try:
        backfill_people(conn)
        print("\n✅ People backfill complete!")
    finally:
        conn.close()