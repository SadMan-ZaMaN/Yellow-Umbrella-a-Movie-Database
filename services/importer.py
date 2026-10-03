"""
Pulls titles and people from TMDB (movies, TV, anime) and RAWG (games) and
saves them into our schema. The search routes call this when a query has
no hits in the local database, so the catalogue grows as people search.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_BASE   = "https://api.themoviedb.org/3"
RAWG_BASE   = "https://api.rawg.io/api"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
HEADERS     = {
    "Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}",
    "accept": "application/json"
}

def tmdb_get(path, params=None):
    res = requests.get(f"{TMDB_BASE}/{path}", headers=HEADERS, params=params, timeout=15)
    res.raise_for_status()
    return res.json()

# ── Helpers ──────────────────────────────────────────────────
def ensure_genre(conn, name):
    rows = conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)
    if rows:
        return rows[0][0]
    conn.run("INSERT INTO genre (genrename) VALUES (:n);", n=name)
    return conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)[0][0]

def ensure_person(conn, tmdb_person):
    name = tmdb_person.get("name", "Unknown")
    profile_path = tmdb_person.get("profile_path")
    photourl = f"{POSTER_BASE}{profile_path}" if profile_path else None
    
    rows = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)
    if rows:
        # Update existing person's photourl if it was missing but we now have it
        if photourl:
            conn.run("UPDATE person SET photourl = :u WHERE personid = :id AND (photourl IS NULL OR photourl = 'None');", u=photourl, id=rows[0][0])
        return rows[0][0]
        
    conn.run("INSERT INTO person (name, photourl) VALUES (:n, :u);", n=name, u=photourl)
    return conn.run("SELECT personid FROM person WHERE name=:n;", n=name)[0][0]

# ── Auto-import a movie from TMDB ────────────────────────────
def fetch_and_save_movie(conn, tmdb_id):
    data    = tmdb_get(f"movie/{tmdb_id}")
    credits = tmdb_get(f"movie/{tmdb_id}/credits")
    title   = data.get("title", "Unknown")

    # Double-check not already in DB
    existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
    if existing:
        return existing[0][0]

    releasedate = data.get("release_date") or None
    posterurl   = f"{POSTER_BASE}{data['poster_path']}" if data.get("poster_path") else None
    avgrating   = data.get("vote_average") or None
    durationmin = data.get("runtime") or None
    boxoffice   = data.get("revenue") or None
    if boxoffice == 0:
        boxoffice = None

    conn.run(
        "INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'movie');",
        t=title, r=releasedate, p=posterurl, a=avgrating)
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
            "INSERT INTO cast_member (mediaid, actorid, rolename, billingorder) VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;",
            m=mediaid, a=pid, r=member.get("character", ""), b=member.get("order", 0) + 1)

    for crew in credits.get("crew", []):
        if crew.get("job") == "Director":
            pid = ensure_person(conn, crew)
            if not conn.run("SELECT 1 FROM director WHERE directorid=:id;", id=pid):
                conn.run("INSERT INTO director (directorid) VALUES (:id);", id=pid)
            conn.run(
                "INSERT INTO media_director (mediaid, directorid) VALUES (:m, :d) ON CONFLICT DO NOTHING;",
                m=mediaid, d=pid)

    fetch_and_save_trailers(conn, mediaid, tmdb_id, media_type="movie")     # fetch trailers for this movie
    print(f"[auto-import] movie saved: {title}")
    return mediaid

# ── Auto-import a series/anime from TMDB ─────────────────────
def fetch_and_save_series(conn, tmdb_id, mediatype="series"):
    data  = tmdb_get(f"tv/{tmdb_id}")
    title = data.get("name", "Unknown")

    existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
    if existing:
        return existing[0][0]

    releasedate  = data.get("first_air_date") or None
    posterurl    = f"{POSTER_BASE}{data['poster_path']}" if data.get("poster_path") else None
    avgrating    = data.get("vote_average") or None
    totalseasons = data.get("number_of_seasons") or None
    tmdb_status  = data.get("status", "")
    status = ("Ongoing"  if tmdb_status == "Returning Series" else
              "Ended"    if tmdb_status == "Ended"            else
              "Canceled" if tmdb_status == "Canceled"         else None)

    conn.run(
        "INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, :mt);",
        t=title, r=releasedate, p=posterurl, a=avgrating, mt=mediatype)
    mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]

    credits = tmdb_get(f"tv/{tmdb_id}/credits")

    if mediatype == "anime":
        studio = data.get("production_companies", [{}])[0].get("name") if data.get("production_companies") else None
        conn.run(
            "INSERT INTO anime (animeid, totalseasons, totalepisodes, studio_name, status) VALUES (:id, :ts, :te, :sn, :st);",
            id=mediaid, ts=totalseasons,
            te=data.get("number_of_episodes"),
            sn=studio, st=status)
    else:
        conn.run(
            "INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st);",
            id=mediaid, ts=totalseasons, st=status)

    for g in data.get("genres", []):
        gid = ensure_genre(conn, g["name"])
        conn.run("INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                 m=mediaid, g=gid)

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

    fetch_and_save_trailers(conn, mediaid, tmdb_id, media_type="tv")    # fetch trailers for this series/anime
    print(f"[auto-import] {mediatype} saved: {title}")
    return mediaid

# ── Auto-import a person from TMDB ───────────────────────────
def fetch_and_save_person(conn, tmdb_id):
    data = tmdb_get(f"person/{tmdb_id}")
    name = data.get("name", "Unknown")

    existing = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)
    if existing:
        return existing[0][0]

    bio      = data.get("biography") or None
    photourl = f"{POSTER_BASE}{data['profile_path']}" if data.get("profile_path") else None
    birthday = data.get("birthday") or None

    conn.run(
        "INSERT INTO person (name, bio, photourl, birthdate) VALUES (:n, :b, :p, :bd);",
        n=name, b=bio, p=photourl, bd=birthday)
    personid = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)[0][0]

    known_for = data.get("known_for_department", "")
    if known_for == "Acting":
        conn.run("INSERT INTO actor (actorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=personid)
    elif known_for == "Directing":
        conn.run("INSERT INTO director (directorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=personid)

    print(f"[auto-import] person saved: {name}")
    return personid

# ── Auto-import a game from RAWG ─────────────────────────────
def fetch_and_save_game(conn, rawg_id):
    res  = requests.get(f"{RAWG_BASE}/games/{rawg_id}",
                        params={"key": os.getenv("RAWG_KEY")}, timeout=15)
    data = res.json()
    title = data.get("name", "Unknown")

    existing = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)
    if existing:
        return existing[0][0]

    releasedate = data.get("released") or None
    posterurl   = data.get("background_image") or None
    avgrating   = data.get("rating") or None
    platforms   = ", ".join([p["platform"]["name"] for p in data.get("platforms", [])[:5]])
    developer   = data.get("developers", [{}])[0].get("name") if data.get("developers") else None
    publisher   = data.get("publishers", [{}])[0].get("name") if data.get("publishers") else None

    conn.run(
        "INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'game');",
        t=title, r=releasedate, p=posterurl, a=avgrating)
    mediaid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
    conn.run(
        "INSERT INTO game (gameid, developer, publisher, platform) VALUES (:id, :dev, :pub, :pl);",
        id=mediaid, dev=developer, pub=publisher, pl=platforms)

    for g in data.get("genres", []):
        gid = ensure_genre(conn, g["name"])
        conn.run("INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                 m=mediaid, g=gid)

    # Fetch trailers (movies) for game
    try:
        movie_res = requests.get(f"{RAWG_BASE}/games/{rawg_id}/movies",
                                 params={"key": os.getenv("RAWG_KEY")}, timeout=15)
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
    except Exception as e:
        print(f"[trailer fetch error] {e}")

    print(f"[auto-import] game saved: {title}")
    return mediaid


def fetch_and_save_trailers(conn, mediaid, tmdb_id, media_type="movie"):
    """Fetch trailer from TMDB and save YouTube link to trailer table"""
    try:
        if media_type == "movie":
            data = tmdb_get(f"movie/{tmdb_id}/videos")
        else:
            data = tmdb_get(f"tv/{tmdb_id}/videos")

        trailernum = 1
        for video in data.get("results", []):
            # only want YouTube trailers
            if video.get("site") == "YouTube" and video.get("type") == "Trailer":
                youtube_url = f"https://www.youtube.com/embed/{video['key']}"
                # check not already saved
                existing = conn.run(
                    "SELECT 1 FROM trailer WHERE mediaid=:m AND trailernum=:n;",
                    m=mediaid, n=trailernum)
                if not existing:
                    conn.run(
                        "INSERT INTO trailer (mediaid, trailernum, title, url) VALUES (:m, :n, :t, :u);",
                        m=mediaid, n=trailernum,
                        t=video.get("name", "Official Trailer"),
                        u=youtube_url)
                trailernum += 1
                if trailernum > 3:  # save max 3 trailers per title
                    break
    except Exception as e:
        print(f"[trailer fetch error] {e}")