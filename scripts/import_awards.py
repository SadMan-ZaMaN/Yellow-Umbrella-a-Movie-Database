"""
Builds the awards section from Wikidata.

Wikidata records Oscar nominations in full (every nominee, every year) with
the TMDB id of each film and person, so every nominee can be imported
exactly instead of guessed by title. For the Golden Globes, BAFTA, Emmys and
Cannes it mostly records the winners, so those show winners only.

Wipes the existing award tables and rebuilds them.

    python -m scripts.import_awards                 # ceremonies since 2000
    python -m scripts.import_awards --since 2015
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from database import get_db
from services.importer import import_movie, import_person, import_tv, tmdb_get

WIKIDATA = "https://query.wikidata.org/sparql"
USER_AGENT = "YellowUmbrella/1.0 (university DBMS project)"

OSCARS, GLOBES, BAFTA, CANNES, EMMYS = (
    "Academy Awards (Oscars)", "Golden Globes", "BAFTA Film Awards",
    "Cannes Film Festival", "Emmy Awards")

EVENTS = {
    OSCARS: "/statics/awards/academy_awards.jpg",
    GLOBES: "/statics/awards/golden_globes.jpg",
    BAFTA:  "/statics/awards/bafta_awards.jpg",
    CANNES: "/statics/awards/cannes_festival.jpg",
    EMMYS:  "/statics/awards/emmy_awards.jpg",
}

# (Wikidata id, ceremony, category name, what gets nominated)
CATEGORIES = [
    ("Q102427",  OSCARS, "Best Picture",                               "title"),
    ("Q103360",  OSCARS, "Best Director",                              "person"),
    ("Q103916",  OSCARS, "Best Actor",                                 "person"),
    ("Q103618",  OSCARS, "Best Actress",                               "person"),
    ("Q106291",  OSCARS, "Best Supporting Actor",                      "person"),
    ("Q106301",  OSCARS, "Best Supporting Actress",                    "person"),
    ("Q106800",  OSCARS, "Best Animated Feature",                      "title"),
    ("Q1011509", GLOBES, "Best Motion Picture – Drama",                "title"),
    ("Q670282",  GLOBES, "Best Motion Picture – Musical or Comedy",    "title"),
    ("Q1255198", GLOBES, "Best Television Series – Drama",             "title"),
    ("Q586356",  GLOBES, "Best Director",                              "person"),
    ("Q139184",  BAFTA,  "Best Film",                                  "title"),
    ("Q787131",  BAFTA,  "Best Director",                              "person"),
    ("Q179808",  CANNES, "Palme d'Or",                                 "title"),
    ("Q989438",  EMMYS,  "Outstanding Drama Series",                   "title"),
    ("Q2110156", EMMYS,  "Outstanding Comedy Series",                  "title"),
    ("Q989439",  EMMYS,  "Outstanding Lead Actor in a Drama Series",   "person"),
    ("Q989445",  EMMYS,  "Outstanding Lead Actress in a Drama Series", "person"),
]

QUERY = """
SELECT ?award ?item ?itemLabel ?year ?won ?movie ?tv ?person ?human
       ?forWork ?forWorkLabel ?forMovie ?forTv WHERE {
  VALUES ?award { %(awards)s }
  { ?item p:P1411 ?st . ?st ps:P1411 ?award . BIND(false AS ?won) }   # nominated for
  UNION
  { ?item p:P166 ?st . ?st ps:P166 ?award . BIND(true AS ?won) }      # award received
  OPTIONAL { ?st pq:P805 ?ceremony . ?ceremony wdt:P585 ?ceremonyDate . }
  OPTIONAL { ?st pqv:P585 ?dateValue . ?dateValue wikibase:timeValue ?date ;
                                                  wikibase:timePrecision ?precision . }
  # For the Oscars, Globes and BAFTA a bare year with no ceremony named is
  # sometimes the film's release year rather than the ceremony's, so there
  # we only trust full dates or named ceremonies. At Cannes and the Emmys
  # the two are the same year.
  FILTER(BOUND(?ceremonyDate) || ?precision >= 11 || ?award IN (%(same_year)s))
  BIND(YEAR(COALESCE(?ceremonyDate, ?date)) AS ?year)
  FILTER(?year >= %(since)d)
  OPTIONAL { ?item wdt:P4947 ?movie . }       # TMDB movie id
  OPTIONAL { ?item wdt:P4983 ?tv . }          # TMDB TV id
  OPTIONAL { ?item wdt:P4985 ?person . }      # TMDB person id
  OPTIONAL { ?item wdt:P21 ?human . }         # has a gender, so it's a person
  OPTIONAL { ?st pq:P1686 ?forWork .          # "for work": the film an actor or
             OPTIONAL { ?forWork wdt:P4947 ?forMovie . }   # producer was nominated for
             OPTIONAL { ?forWork wdt:P4983 ?forTv . } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def _value(binding, key):
    return binding[key]["value"] if key in binding else None


def fetch_nominations(since):
    """{(category index, item, year): nomination} from Wikidata."""
    by_award = {qid: i for i, (qid, *_rest) in enumerate(CATEGORIES)}
    same_year = [qid for qid, event, *_rest in CATEGORIES if event in (CANNES, EMMYS)]
    query = QUERY % {"awards": " ".join(f"wd:{q}" for q in by_award), "since": since,
                     "same_year": ", ".join(f"wd:{q}" for q in same_year)}
    res = requests.get(WIKIDATA, params={"query": query, "format": "json"},
                       headers={"User-Agent": USER_AGENT}, timeout=180)
    res.raise_for_status()

    noms = {}
    for b in res.json()["results"]["bindings"]:
        cat = by_award[_value(b, "award").rsplit("/", 1)[-1]]
        row = {k: _value(b, k) for k in ("item", "itemLabel", "movie", "tv", "person", "human",
                                         "forWork", "forWorkLabel", "forMovie", "forTv")}
        is_person = row["person"] or row["human"]
        if CATEGORIES[cat][3] == "title" and is_person and row["forWork"]:
            # For some years Best Picture is only recorded on the producers
            # ("Emma Thomas, for Oppenheimer"). Count it as the film's
            # nomination; several producers fold into one entry below.
            row = {"item": row["forWork"], "itemLabel": row["forWorkLabel"],
                   "movie": row["forMovie"], "tv": row["forTv"]}
        key = (cat, row["item"], int(_value(b, "year")))
        nom = noms.setdefault(key, {"label": row["itemLabel"], "won": False})
        # a winner usually has both a "nominated" and a "received" statement
        nom["won"] |= _value(b, "won") == "true"
        for field in ("movie", "tv", "person", "human", "forWorkLabel"):
            nom[field] = nom.get(field) or row.get(field)
    return noms


# ── Finding things on TMDB that Wikidata has no id for ───────

def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _has_label(text):
    return text and not re.fullmatch(r"Q\d+", text)     # unlabelled items come back as their id


def find_movie(title, ceremony_year):
    # films usually come out the year before their ceremony
    for params in ({"primary_release_year": ceremony_year - 1}, {}):
        results = tmdb_get("search/movie", {"query": title, **params}).get("results", [])
        exact = [r for r in results if _norm(r["title"]) == _norm(title)]
        if exact:
            return exact[0]["id"]
    return None


def find_person(name):
    results = tmdb_get("search/person", {"query": name}).get("results", [])
    exact = [r for r in results if _norm(r["name"]) == _norm(name)]
    return exact[0]["id"] if exact else None


def resolve(nom, kind, year):
    """("movie"|"tv"|"person", TMDB id), None if the entry isn't something we
    store (a producer under Best Picture, a film under Best Director), or
    "missed" if it should be but TMDB has no exact match."""
    is_person = nom["person"] or nom["human"]
    if kind == "person":
        if nom["person"]:
            return "person", int(nom["person"])
        if not nom["human"] or not _has_label(nom["label"]):
            return None
        found = find_person(nom["label"])
        return ("person", found) if found else "missed"

    if nom["movie"]:
        return "movie", int(nom["movie"])
    if nom["tv"]:
        return "tv", int(nom["tv"])
    if is_person or not _has_label(nom["label"]):
        return None
    found = find_movie(nom["label"], year)
    return ("movie", found) if found else "missed"


# ── Importing ────────────────────────────────────────────────

IMPORTERS = {"movie": import_movie, "tv": import_tv, "person": import_person}


def import_one(ext):
    kind, tmdb_id = ext
    conn = get_db()
    try:
        for attempt in range(3):
            try:
                return ext, IMPORTERS[kind](conn, tmdb_id)
            except Exception as e:
                if attempt == 2:
                    print(f"  couldn't import {kind} {tmdb_id}: {e}")
        return ext, None
    finally:
        conn.close()


def main(since=2000):
    print(f"Fetching nominations since {since} from Wikidata...")
    noms = fetch_nominations(since)
    print(f"  {len(noms)} nominations")

    print("Matching them to TMDB...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        resolved = dict(zip(noms, pool.map(
            lambda key: resolve(noms[key], CATEGORIES[key[0]][3], key[2]), noms)))
    missed = sorted({noms[k]["label"] for k, v in resolved.items() if v == "missed"})
    resolved = {k: (v if v != "missed" else None) for k, v in resolved.items()}

    wanted = sorted({ext for ext in resolved.values() if ext})
    print(f"Importing {len(wanted)} titles and people (already imported ones are skipped)...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        local = dict(pool.map(import_one, wanted))

    print("Rebuilding the award tables...")
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run("TRUNCATE nomination, media_nom, person_nom, award_category, award_event RESTART IDENTITY CASCADE;")
        events = {name: conn.run("INSERT INTO award_event (name, imageurl) VALUES (:n, :i) RETURNING eventid;",
                                 n=name, i=image)[0][0]
                  for name, image in EVENTS.items()}
        categories = {}
        for _qid, _event, name, _kind in CATEGORIES:
            if name not in categories:
                categories[name] = conn.run("INSERT INTO award_category (name) VALUES (:n) RETURNING categoryid;",
                                            n=name)[0][0]

        # Wikidata sometimes has two items for the same film; once resolved
        # to our own ids they collapse into one nomination
        final = {}
        for (cat, _item, year), nom in noms.items():
            ext = resolved[(cat, _item, year)]
            local_id = local.get(ext) if ext else None
            if not local_id:
                continue
            entry = final.setdefault((cat, ext[0] == "person", local_id, year), {"won": False, "subtitle": None})
            entry["won"] |= nom["won"]
            if ext[0] == "person" and _has_label(nom["forWorkLabel"]):
                entry["subtitle"] = entry["subtitle"] or nom["forWorkLabel"]

        for (cat, is_person, local_id, year), entry in sorted(final.items(), key=lambda kv: (kv[0][3], kv[0][0])):
            _qid, event, category, _kind = CATEGORIES[cat]
            nomid = conn.run(
                """INSERT INTO nomination (eventid, categoryid, year, iswinner)
                   VALUES (:e, :c, :y, :w) RETURNING nominationid;""",
                e=events[event], c=categories[category], y=year, w=entry["won"])[0][0]
            if is_person:
                conn.run("INSERT INTO person_nom (nomid, personid, subtitle) VALUES (:n, :p, :s);",
                         n=nomid, p=local_id, s=entry["subtitle"])
            else:
                conn.run("INSERT INTO media_nom (nomid, mediaid) VALUES (:n, :m);", n=nomid, m=local_id)
        added = len(final)
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise
    finally:
        conn.close()

    print(f"\nDone: {added} nominations across {len(EVENTS)} ceremonies.")
    if missed:
        print(f"No exact TMDB match for {len(missed)}: {', '.join(missed)}")


if __name__ == "__main__":
    since = int(sys.argv[sys.argv.index("--since") + 1]) if "--since" in sys.argv else 2000
    main(since)
