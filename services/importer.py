"""
Pulls titles and people from TMDB (movies, TV, anime) and RAWG (games) and
saves them into our schema.

Nothing is imported while you search. A title is only saved when someone
opens it (see /open in routes/discover.py) or a script imports it, so the
database doesn't fill up with whatever happened to match a half-typed query.
"""
import os
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_BASE     = "https://api.themoviedb.org/3"
RAWG_BASE     = "https://api.rawg.io/api"
IMAGE_BASE    = "https://image.tmdb.org/t/p"
POSTER_BASE   = f"{IMAGE_BASE}/w500"
HEADERS       = {
    "Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}",
    "accept": "application/json"
}

ANIMATION_GENRE = 16   # TMDB's id for "Animation"


# ── HTTP with a small in-memory cache ────────────────────────
# Search-as-you-type and the home page ask for the same things over and
# over, so successful responses can be kept for `ttl` seconds.

_cache = {}
_cache_lock = threading.Lock()


def _get_json(url, params, headers, ttl):
    key = (url, tuple(sorted((params or {}).items())))
    now = time.time()
    if ttl:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and hit[0] > now:
                return hit[1]

    # RAWG in particular times out or 502s when it's busy - retry a couple of times
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, params=params, timeout=15)
            if res.status_code < 500:
                break
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt == 2:
                # the message would include the URL, and with it the API key
                raise requests.RequestException(f"{url.split('?')[0]}: {type(e).__name__}") from None
        time.sleep(1 + attempt * 2)
    if not res.ok:
        raise requests.HTTPError(f"{res.status_code} from {url.split('?')[0]}")
    data = res.json()

    if ttl:
        with _cache_lock:
            if len(_cache) > 1000:
                _cache.clear()
            _cache[key] = (now + ttl, data)
    return data


def tmdb_get(path, params=None, ttl=0):
    return _get_json(f"{TMDB_BASE}/{path}", params, HEADERS, ttl)


def rawg_get(path, params=None, ttl=0):
    params = {**(params or {}), "key": os.getenv("RAWG_KEY")}
    return _get_json(f"{RAWG_BASE}/{path}", params, None, ttl)


def tmdb_image(path, size="w500"):
    return f"{IMAGE_BASE}/{size}{path}" if path else None


def is_anime(show: dict) -> bool:
    """Japanese animated TV. Works on both search results and full details."""
    genre_ids = show.get("genre_ids") or [g["id"] for g in show.get("genres", [])]
    japanese = "JP" in (show.get("origin_country") or []) or show.get("original_language") == "ja"
    return ANIMATION_GENRE in genre_ids and japanese


# ── Lookups ──────────────────────────────────────────────────

def find_media(conn, kind: str, ext_id: int):
    """Local mediaid for a TMDB movie/tv id or a RAWG game id, or None."""
    if kind == "movie":
        rows = conn.run("SELECT mediaid FROM media WHERE mediatype='movie' AND tmdb_id=:id;", id=ext_id)
    elif kind == "tv":
        rows = conn.run("SELECT mediaid FROM media WHERE mediatype IN ('series','anime') AND tmdb_id=:id;", id=ext_id)
    elif kind == "game":
        rows = conn.run("SELECT mediaid FROM media WHERE rawg_id=:id;", id=ext_id)
    else:
        raise ValueError(kind)
    return rows[0][0] if rows else None


def _find_legacy(conn, title, year, mediatypes):
    """(mediaid, mediatype) of a row saved before we kept external ids,
    matched on title + year, or (None, None)."""
    rows = conn.run(
        """SELECT mediaid, mediatype FROM media
           WHERE tmdb_id IS NULL AND rawg_id IS NULL
             AND mediatype = ANY(:mtypes)
             AND LOWER(title) = LOWER(:t)
             AND (releasedate IS NULL OR :y = '' OR EXTRACT(YEAR FROM releasedate)::text = :y)
           ORDER BY mediaid LIMIT 1;""",
        mtypes=list(mediatypes), t=title, y=year or "")
    return (rows[0][0], rows[0][1]) if rows else (None, None)


def _atomic(conn, work):
    conn.run("BEGIN")
    try:
        result = work()
        conn.run("COMMIT")
        return result
    except Exception:
        conn.run("ROLLBACK")
        raise


# ── Shared bits ──────────────────────────────────────────────

def ensure_genre(conn, name):
    rows = conn.run("SELECT genreid FROM genre WHERE genrename=:n;", n=name)
    if rows:
        return rows[0][0]
    return conn.run("INSERT INTO genre (genrename) VALUES (:n) RETURNING genreid;", n=name)[0][0]


def ensure_person(conn, tmdb_person):
    """personid for someone from a TMDB credits list, creating them if needed."""
    name     = tmdb_person.get("name", "Unknown")
    tmdb_id  = tmdb_person.get("id")
    photourl = tmdb_image(tmdb_person.get("profile_path"))

    if tmdb_id:
        rows = conn.run("SELECT personid FROM person WHERE tmdb_id=:id;", id=tmdb_id)
        if rows:
            return rows[0][0]

    rows = conn.run("SELECT personid FROM person WHERE name=:n AND tmdb_id IS NULL ORDER BY personid LIMIT 1;", n=name)
    if rows:
        conn.run("""UPDATE person SET tmdb_id = :tid,
                        photourl = COALESCE(NULLIF(NULLIF(photourl, ''), 'None'), :u)
                    WHERE personid = :id;""", tid=tmdb_id, u=photourl, id=rows[0][0])
        return rows[0][0]

    return conn.run(
        "INSERT INTO person (name, photourl, tmdb_id) VALUES (:n, :u, :tid) RETURNING personid;",
        n=name, u=photourl, tid=tmdb_id)[0][0]


def _set_genres(conn, mediaid, genres):
    for g in genres:
        conn.run("INSERT INTO media_genre (mediaid, genreid) VALUES (:m, :g) ON CONFLICT DO NOTHING;",
                 m=mediaid, g=ensure_genre(conn, g["name"]))


def _set_credits(conn, mediaid, cast, directors):
    for member in cast[:10]:
        pid = ensure_person(conn, member)
        conn.run("INSERT INTO actor (actorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=pid)
        conn.run(
            """INSERT INTO cast_member (mediaid, actorid, rolename, billingorder)
               VALUES (:m, :a, :r, :b) ON CONFLICT DO NOTHING;""",
            m=mediaid, a=pid, r=member.get("character", ""), b=member.get("order", 0) + 1)

    for person in directors:
        pid = ensure_person(conn, person)
        conn.run("INSERT INTO director (directorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=pid)
        conn.run("INSERT INTO media_director (mediaid, directorid) VALUES (:m, :d) ON CONFLICT DO NOTHING;",
                 m=mediaid, d=pid)


def _set_trailers(conn, mediaid, videos):
    """Up to 3 YouTube trailers, as embed links."""
    trailers = [v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
    for num, video in enumerate(trailers[:3], start=1):
        conn.run(
            """INSERT INTO trailer (mediaid, trailernum, title, url) VALUES (:m, :n, :t, :u)
               ON CONFLICT (mediaid, trailernum) DO NOTHING;""",
            m=mediaid, n=num, t=video.get("name", "Official Trailer"),
            u=f"https://www.youtube.com/embed/{video['key']}")


def save_media(conn, mediaid, fields):
    """Insert a new media row (mediaid None) or refresh an existing one."""
    if mediaid is None:
        cols = ", ".join(fields)
        vals = ", ".join(f":{k}" for k in fields)
        return conn.run(
            f"INSERT INTO media ({cols}, avgrating) VALUES ({vals}, :tmdb_rating) RETURNING mediaid;",
            **fields)[0][0]

    # keep the existing title and type, refresh everything else
    fields = {k: v for k, v in fields.items() if k not in ("title", "mediatype")}
    sets = ", ".join(f"{k} = :{k}" for k in fields if k != "releasedate")
    conn.run(f"""UPDATE media SET {sets}, releasedate = COALESCE(releasedate, :releasedate)
                 WHERE mediaid = :mediaid;""", mediaid=mediaid, **fields)
    # re-blend with our reviews (sql/functions.sql)
    conn.run("SELECT refresh_avg_rating(:id);", id=mediaid)
    return mediaid


def _import(conn, kind, ext_id, fetch, store):
    """Common shape of every import: return the local row if we have it,
    otherwise fetch from the API and store it in a single transaction."""
    existing = find_media(conn, kind, ext_id)
    if existing:
        return existing
    data = fetch()
    try:
        return _atomic(conn, lambda: store(data))
    except Exception:
        # two requests importing the same title at once - the other one won
        existing = find_media(conn, kind, ext_id)
        if existing:
            return existing
        raise


# ── Movies ───────────────────────────────────────────────────

def movie_fields(d):
    return {
        "title":       d.get("title") or "Unknown",
        "releasedate": d.get("release_date") or None,
        "posterurl":   tmdb_image(d.get("poster_path")),
        "backdropurl": tmdb_image(d.get("backdrop_path"), "w1280"),
        "overview":    d.get("overview") or None,
        "mediatype":   "movie",
        "tmdb_id":     d["id"],
        "tmdb_rating": round(d["vote_average"], 2) if d.get("vote_count") else None,
        "vote_count":  d.get("vote_count") or 0,
        "popularity":  d.get("popularity"),
    }


def import_movie(conn, tmdb_id):
    def fetch():
        return tmdb_get(f"movie/{tmdb_id}", {"append_to_response": "credits,videos"})

    def store(d):
        fields = movie_fields(d)
        mediaid, _ = _find_legacy(conn, fields["title"], (fields["releasedate"] or "")[:4], ["movie"])
        mediaid = save_media(conn, mediaid, fields)
        conn.run(
            """INSERT INTO movie (movieid, durationmin, boxoffice) VALUES (:id, :d, :b)
               ON CONFLICT (movieid) DO UPDATE
               SET durationmin = EXCLUDED.durationmin, boxoffice = EXCLUDED.boxoffice;""",
            id=mediaid, d=d.get("runtime") or None, b=d.get("revenue") or None)
        _set_genres(conn, mediaid, d.get("genres", []))
        crew = d.get("credits", {}).get("crew", [])
        _set_credits(conn, mediaid, d.get("credits", {}).get("cast", []),
                     [c for c in crew if c.get("job") == "Director"])
        _set_trailers(conn, mediaid, d.get("videos", {}).get("results", []))
        print(f"[import] movie: {fields['title']}")
        return mediaid

    return _import(conn, "movie", tmdb_id, fetch, store)


# ── Series and anime ─────────────────────────────────────────

def _tv_status(s):
    return {"Returning Series": "Ongoing", "Ended": "Ended", "Canceled": "Canceled"}.get(s)


def tv_fields(d, mediatype):
    return {
        "title":       d.get("name") or "Unknown",
        "releasedate": d.get("first_air_date") or None,
        "posterurl":   tmdb_image(d.get("poster_path")),
        "backdropurl": tmdb_image(d.get("backdrop_path"), "w1280"),
        "overview":    d.get("overview") or None,
        "mediatype":   mediatype,
        "tmdb_id":     d["id"],
        "tmdb_rating": round(d["vote_average"], 2) if d.get("vote_count") else None,
        "vote_count":  d.get("vote_count") or 0,
        "popularity":  d.get("popularity"),
    }


def import_tv(conn, tmdb_id, mediatype=None):
    """Imports a TV show as 'series' or 'anime' (decided from TMDB if not given)."""
    def fetch():
        return tmdb_get(f"tv/{tmdb_id}", {"append_to_response": "credits,videos"})

    def store(d):
        title = d.get("name") or "Unknown"
        mediaid, existing_type = _find_legacy(conn, title, (d.get("first_air_date") or "")[:4],
                                              ["series", "anime"])
        # an existing row keeps its type, it already sits in that child table
        kind = existing_type or mediatype or ("anime" if is_anime(d) else "series")
        fields = tv_fields(d, kind)
        mediaid = save_media(conn, mediaid, fields)
        status = _tv_status(d.get("status"))

        if kind == "anime":
            studio = (d.get("production_companies") or [{}])[0].get("name")
            conn.run(
                """INSERT INTO anime (animeid, totalseasons, totalepisodes, studio_name, status)
                   VALUES (:id, :ts, :te, :sn, :st) ON CONFLICT (animeid) DO NOTHING;""",
                id=mediaid, ts=d.get("number_of_seasons"), te=d.get("number_of_episodes"),
                sn=studio, st=status)
        else:
            conn.run(
                """INSERT INTO series (seriesid, totalseasons, status) VALUES (:id, :ts, :st)
                   ON CONFLICT (seriesid) DO NOTHING;""",
                id=mediaid, ts=d.get("number_of_seasons"), st=status)

        _set_genres(conn, mediaid, d.get("genres", []))
        # for TV the "director" we show is whoever created the show
        creators = d.get("created_by") or [c for c in d.get("credits", {}).get("crew", [])
                                           if c.get("job") == "Director"][:2]
        _set_credits(conn, mediaid, d.get("credits", {}).get("cast", []), creators)
        _set_trailers(conn, mediaid, d.get("videos", {}).get("results", []))
        print(f"[import] {kind}: {fields['title']}")
        return mediaid

    return _import(conn, "tv", tmdb_id, fetch, store)


# ── Games (RAWG) ─────────────────────────────────────────────

ESRB_CODES = {"Everyone": "E", "Everyone 10+": "E10+", "Teen": "T", "Mature": "M",
              "Adults Only": "AO", "Rating Pending": "RP"}


def game_fields(d):
    return {
        "title":       d.get("name") or "Unknown",
        "releasedate": d.get("released") or None,
        "posterurl":   d.get("background_image"),
        "backdropurl": d.get("background_image_additional") or d.get("background_image"),
        "overview":    d.get("description_raw") or None,
        "mediatype":   "game",
        "rawg_id":     d["id"],
        # RAWG rates out of 5, everything else on the site is out of 10
        "tmdb_rating": round(d["rating"] * 2, 2) if d.get("ratings_count") else None,
        "vote_count":  d.get("ratings_count") or 0,
        "popularity":  d.get("added"),
    }


def import_game(conn, rawg_id):
    def fetch():
        return rawg_get(f"games/{rawg_id}")

    def store(d):
        fields = game_fields(d)
        mediaid, _ = _find_legacy(conn, fields["title"], (fields["releasedate"] or "")[:4], ["game"])
        mediaid = save_media(conn, mediaid, fields)
        esrb = (d.get("esrb_rating") or {}).get("name")
        conn.run(
            """INSERT INTO game (gameid, developer, publisher, platform, esrb_rating)
               VALUES (:id, :dev, :pub, :pl, :esrb) ON CONFLICT (gameid) DO NOTHING;""",
            id=mediaid,
            dev=(d.get("developers") or [{}])[0].get("name"),
            pub=(d.get("publishers") or [{}])[0].get("name"),
            pl=", ".join(p["platform"]["name"] for p in (d.get("platforms") or [])[:5]),
            esrb=ESRB_CODES.get(esrb))
        _set_genres(conn, mediaid, d.get("genres", []))
        print(f"[import] game: {fields['title']}")
        return mediaid

    mediaid = _import(conn, "game", rawg_id, fetch, store)
    _save_game_trailers(conn, mediaid, rawg_id)
    return mediaid


def _save_game_trailers(conn, mediaid, rawg_id):
    if conn.run("SELECT 1 FROM trailer WHERE mediaid=:m;", m=mediaid):
        return
    try:
        videos = rawg_get(f"games/{rawg_id}/movies").get("results", [])
    except requests.RequestException as e:
        print(f"[import] no trailers for game {rawg_id}: {e}")
        return
    for num, video in enumerate(videos[:3], start=1):
        url = (video.get("data") or {}).get("max") or (video.get("data") or {}).get("480")
        if url:
            conn.run("""INSERT INTO trailer (mediaid, trailernum, title, url) VALUES (:m, :n, :t, :u)
                        ON CONFLICT DO NOTHING;""",
                     m=mediaid, n=num, t=video.get("name", "Game Trailer"), u=url)


# ── People ───────────────────────────────────────────────────

def import_person(conn, tmdb_id):
    rows = conn.run("SELECT personid FROM person WHERE tmdb_id=:id;", id=tmdb_id)
    if rows:
        return rows[0][0]

    d = tmdb_get(f"person/{tmdb_id}")

    def store():
        personid = ensure_person(conn, d)
        conn.run("""UPDATE person SET bio = COALESCE(:b, bio), birthdate = COALESCE(:bd, birthdate),
                        photourl = COALESCE(:p, photourl)
                    WHERE personid = :id;""",
                 b=d.get("biography") or None, bd=d.get("birthday") or None,
                 p=tmdb_image(d.get("profile_path")), id=personid)
        if d.get("known_for_department") == "Directing":
            conn.run("INSERT INTO director (directorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=personid)
        else:
            conn.run("INSERT INTO actor (actorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=personid)
        print(f"[import] person: {d.get('name')}")
        return personid

    return _atomic(conn, store)


# ── Topping up older rows ────────────────────────────────────

def fill_missing_details(conn, mediaid, kind, d):
    """Add genres / cast / trailers to a row that has none yet.
    `d` is a TMDB movie or tv response fetched with credits,videos appended."""
    has = lambda table: conn.run(f"SELECT 1 FROM {table} WHERE mediaid=:m LIMIT 1;", m=mediaid)
    if not has("media_genre"):
        _set_genres(conn, mediaid, d.get("genres", []))
    if not has("cast_member"):
        crew = d.get("credits", {}).get("crew", [])
        directors = (d.get("created_by") if kind == "tv" else None) or \
            [c for c in crew if c.get("job") == "Director"][:2]
        _set_credits(conn, mediaid, d.get("credits", {}).get("cast", []), directors)
    if not has("trailer"):
        _set_trailers(conn, mediaid, d.get("videos", {}).get("results", []))
