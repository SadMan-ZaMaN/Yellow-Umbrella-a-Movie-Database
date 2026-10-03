"""
Read-only lookups against TMDB / RAWG for search and the home page.

Results come back in one shape whatever their source:

    {"type": "movie", "title": ..., "year": ..., "poster": ..., "backdrop": ...,
     "rating": ..., "popularity": ..., "url": ...}

`url` points at the local page when we already have the title, otherwise at
/open/<kind>/<id>, which imports it on the first click.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests

from services.importer import is_anime, rawg_get, tmdb_get, tmdb_image

SEARCH_TTL   = 10 * 60      # seconds
TRENDING_TTL = 60 * 60

PAGE_FOR = {"movie": "movie", "series": "series", "anime": "anime", "game": "game", "person": "person"}


def _year(value):
    return (value or "")[:4] or None


# ── Converting API results ───────────────────────────────────

def _from_tmdb(item, kind=None):
    kind = kind or item.get("media_type")
    if kind == "person":
        return {
            "type": "person", "ext": ("person", item["id"]),
            "title": item.get("name"), "year": None,
            "poster": tmdb_image(item.get("profile_path"), "w185"), "backdrop": None,
            "rating": None, "popularity": item.get("popularity") or 0,
            "subtitle": item.get("known_for_department"),
        }
    if kind == "movie":
        title, released, ext = item.get("title"), item.get("release_date"), ("movie", item["id"])
        mediatype = "movie"
    else:
        title, released, ext = item.get("name"), item.get("first_air_date"), ("tv", item["id"])
        mediatype = "anime" if is_anime(item) else "series"
    return {
        "type": mediatype, "ext": ext, "title": title, "year": _year(released),
        "poster": tmdb_image(item.get("poster_path"), "w342"),
        "backdrop": tmdb_image(item.get("backdrop_path"), "w1280"),
        "rating": round(item["vote_average"], 1) if item.get("vote_count") else None,
        # TMDB popularity is this week's buzz; adding the vote count lets
        # something famous but quiet right now still rank well
        "popularity": (item.get("popularity") or 0) + (item.get("vote_count") or 0) / 100,
        "overview": item.get("overview"),
    }


def _from_rawg(item):
    return {
        "type": "game", "ext": ("game", item["id"]), "title": item.get("name"),
        "year": _year(item.get("released")),
        "poster": item.get("background_image"), "backdrop": item.get("background_image"),
        "rating": round(item["rating"] * 2, 1) if item.get("ratings_count") else None,
        # RAWG's "added" (people who own/want it) runs into the tens of
        # thousands; scaled down so games rank fairly next to films and shows
        "popularity": (item.get("added") or 0) / 100,
    }


LOCAL_COLUMNS = "mediaid, title, mediatype, releasedate, posterurl, avgrating, popularity, vote_count, backdropurl"


def _from_row(row):
    mediaid, title, mediatype, released, poster, rating, popularity, votes, backdrop = row
    if mediatype == "game":
        fame = float(popularity or 0) / 100
    else:
        fame = float(popularity or 0) + (votes or 0) / 100
    return {
        "type": mediatype, "id": mediaid, "title": title, "year": _year(str(released or "")),
        "poster": poster, "backdrop": backdrop,
        "rating": round(float(rating), 1) if rating is not None else None,
        "popularity": fame,
        "url": f"/{PAGE_FOR[mediatype]}.html?id={mediaid}",
    }


# ── Matching API results to local rows ───────────────────────

def link_local(conn, items):
    """Fill in `id`/`url` for API results we've already imported."""
    by_kind = {}
    for item in items:
        if "ext" in item:
            by_kind.setdefault(item["ext"][0], []).append(item["ext"][1])

    known = {}
    queries = {
        "movie":  "SELECT tmdb_id, mediaid, mediatype FROM media WHERE mediatype='movie' AND tmdb_id = ANY(:ids);",
        "tv":     "SELECT tmdb_id, mediaid, mediatype FROM media WHERE mediatype IN ('series','anime') AND tmdb_id = ANY(:ids);",
        "game":   "SELECT rawg_id, mediaid, mediatype FROM media WHERE rawg_id = ANY(:ids);",
        "person": "SELECT tmdb_id, personid, 'person' FROM person WHERE tmdb_id = ANY(:ids);",
    }
    for kind, ids in by_kind.items():
        for ext_id, local_id, local_type in conn.run(queries[kind], ids=ids):
            known[(kind, ext_id)] = (local_id, local_type)

    for item in items:
        ext = item.pop("ext", None)
        if not ext:
            continue
        if ext in known:
            local_id, local_type = known[ext]
            item["id"], item["type"] = local_id, local_type
            item["url"] = f"/{PAGE_FOR[local_type]}.html?id={local_id}"
        else:
            item["id"] = None
            item["url"] = f"/open/{ext[0]}/{ext[1]}"
    return items


# ── Search ───────────────────────────────────────────────────

def _relevance(title, q):
    t, q = (title or "").lower(), q.lower()
    if t == q:
        return 4
    if t.startswith(q):
        return 2
    if f" {q}" in f" {t}":
        return 1.3     # matches the start of a word
    return 1


def _search_tmdb(q):
    try:
        data = tmdb_get("search/multi", {"query": q, "include_adult": "false"}, ttl=SEARCH_TTL)
    except requests.RequestException as e:
        print(f"[search] TMDB failed: {e}")
        return []
    return [_from_tmdb(r) for r in data.get("results", [])
            if r.get("media_type") in ("movie", "tv", "person")]


def _search_rawg(q):
    try:
        data = rawg_get("games", {"search": q, "page_size": 10, "search_precise": "true"}, ttl=SEARCH_TTL)
    except requests.RequestException as e:
        print(f"[search] RAWG failed: {e}")
        return []
    return [_from_rawg(r) for r in data.get("results", [])]


def _search_local(conn, q):
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = conn.run(
        f"""SELECT {LOCAL_COLUMNS} FROM media WHERE title ILIKE :p
            ORDER BY popularity DESC NULLS LAST LIMIT 40;""", p=pattern)
    return [_from_row(r) for r in rows]


def search(conn, q, limit=30):
    with ThreadPoolExecutor(max_workers=2) as pool:
        tmdb_future = pool.submit(_search_tmdb, q)
        rawg_future = pool.submit(_search_rawg, q)
        local = _search_local(conn, q)
        external = link_local(conn, tmdb_future.result() + rawg_future.result())

    # Older local rows have no TMDB id, so link_local can't spot them.
    # Match those on title + year instead of offering a duplicate import.
    local_by_title = {(r["title"].lower(), r["year"]): r for r in local}
    for item in external:
        if item["id"] is None and item["type"] != "person":
            match = local_by_title.get(((item["title"] or "").lower(), item["year"]))
            if match:
                item.update(id=match["id"], type=match["type"], url=match["url"])

    # an API hit we already have replaces the local copy, it carries the
    # up-to-date popularity
    seen = {r["id"] for r in external if r["id"] and r["type"] != "person"}
    results = external + [r for r in local if r["id"] not in seen]

    # drop the long tail of things nobody has heard of, unless that's all there is
    known = [r for r in results if r["popularity"] >= 1 or r["id"]]
    results = known or results

    results.sort(key=lambda r: _relevance(r["title"], q) * max(r["popularity"], 1), reverse=True)
    return results[:limit]


# ── Trending ─────────────────────────────────────────────────

# Weekly trending on TMDB includes brand-new releases with a handful of
# votes. Requiring some votes keeps the home page to things people know.
MIN_TRENDING_VOTES = 200


def _tmdb_trending(kind, pages=2):
    items = []
    for page in range(1, pages + 1):
        data = tmdb_get(f"trending/{kind}/week", {"page": page}, ttl=TRENDING_TTL)
        items += [r for r in data.get("results", []) if (r.get("vote_count") or 0) >= MIN_TRENDING_VOTES]
    return [_from_tmdb(r, kind) for r in items]


def _trending_movies():
    return _tmdb_trending("movie")


def _trending_series():
    return [s for s in _tmdb_trending("tv") if s["type"] == "series"]


def _trending_anime():
    data = tmdb_get("discover/tv", {
        "with_genres": 16, "with_origin_country": "JP", "sort_by": "popularity.desc",
        "vote_count.gte": 500,
    }, ttl=TRENDING_TTL)
    return [_from_tmdb(r, "tv") for r in data.get("results", [])]


def _trending_games():
    today = date.today()
    data = rawg_get("games", {
        "dates": f"{today - timedelta(days=365)},{today}",
        "ordering": "-added", "page_size": 20,
    }, ttl=TRENDING_TTL)
    return [_from_rawg(r) for r in data.get("results", []) if r.get("background_image")]


TRENDING = {
    "movie": _trending_movies,
    "series": _trending_series,
    "anime": _trending_anime,
    "game": _trending_games,
}


def trending(conn, kind="all", limit=20):
    if kind in TRENDING:
        items = TRENDING[kind]()
    else:
        # a bit of everything, interleaved so one type doesn't take over
        with ThreadPoolExecutor(max_workers=4) as pool:
            lists = list(pool.map(lambda fn: fn(), TRENDING.values()))
        items = []
        for row in zip(*lists):
            items.extend(row)
    items = [i for i in items if i["poster"]]
    return link_local(conn, items[:limit])


def popular_from_db(conn, kind="all", limit=20):
    """Fallback for when the APIs are unreachable."""
    rows = conn.run(
        f"""SELECT {LOCAL_COLUMNS} FROM media
           WHERE posterurl IS NOT NULL AND (:k = 'all' OR mediatype = :k)
           ORDER BY popularity DESC NULLS LAST, vote_count DESC NULLS LAST
           LIMIT :l;""", k=kind, l=limit)
    return [_from_row(r) for r in rows]
