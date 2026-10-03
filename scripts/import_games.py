import requests
import pg8000.native
from dotenv import load_dotenv
import os
import time

load_dotenv()

RAWG_BASE = "https://api.rawg.io/api"
RAWG_KEY = os.getenv("RAWG_KEY")

def get_db():
    return pg8000.native.Connection(
        database=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT"))
    )

def ensure_genre(conn, name):
    rows = conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)
    if rows:
        return rows[0][0]
    conn.run("INSERT INTO genre (genrename) VALUES (:n);", n=name)
    return conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)[0][0]

def import_popular_games(conn, pages=3):
    print("\nImporting popular games...")
    for page in range(1, pages + 1):
        res = requests.get(f"{RAWG_BASE}/games", params={
            "key": RAWG_KEY, "ordering": "-rating", "page": page, "page_size": 20
        })
        data = res.json()
        for g in data.get("results", []):
            title = g.get("name", "Unknown")
            existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
            if existing:
                print(f"  Skipping: {title}")
                continue

            releasedate = g.get("released") or None
            posterurl = g.get("background_image") or None
            platforms = ", ".join([p["platform"]["name"] for p in g.get("platforms", [])[:5]])

            try:
                conn.run(
                    "INSERT INTO media (title, releasedate, posterurl, mediatype) VALUES (:t, :r, :p, 'game');",
                    t=title, r=releasedate, p=posterurl)
                mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
                conn.run(
                    "INSERT INTO game (gameid, platform) VALUES (:id, :pl);",
                    id=mediaid, pl=platforms)

                for genre in g.get("genres", []):
                    gid = ensure_genre(conn, genre["name"])
                    conn.run(
                        "INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                        m=mediaid, g=gid)

                print(f"  ✓ {title}")
                time.sleep(0.25)
            except Exception as e:
                print(f"  ✗ Failed {title}: {e}")

if __name__ == "__main__":
    conn = get_db()
    try:
        import_popular_games(conn, pages=3)   # ~60 games
        print("\n✅ Games import complete!")
    finally:
        conn.close()