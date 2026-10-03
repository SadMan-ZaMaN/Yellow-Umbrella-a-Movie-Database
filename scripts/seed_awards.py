"""
Rebuilds all award data from scratch (wipes existing nominations first).
Handles all Oscars, BAFTA, Golden Globes, Cannes, and Emmy nominations.
"""

import os, sys, time, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from database import get_db

TMDB_BASE = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
HEADERS = {"Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}", "accept": "application/json"}


def tmdb_search_movie(title):
    try:
        r = requests.get(f"{TMDB_BASE}/search/movie", headers=HEADERS,
                         params={"query": title}).json()
        if r.get("results"):
            m = r["results"][0]
            poster = f"{POSTER_BASE}{m['poster_path']}" if m.get("poster_path") else None
            return poster, m.get("release_date"), m.get("vote_average"), m.get("runtime")
        time.sleep(0.25)
    except:
        pass
    return None, None, None, None


def tmdb_search_tv(title):
    try:
        r = requests.get(f"{TMDB_BASE}/search/tv", headers=HEADERS,
                         params={"query": title}).json()
        if r.get("results"):
            m = r["results"][0]
            poster = f"{POSTER_BASE}{m['poster_path']}" if m.get("poster_path") else None
            return poster, m.get("first_air_date"), m.get("vote_average")
        time.sleep(0.25)
    except:
        pass
    return None, None, None


def tmdb_search_person(name):
    try:
        r = requests.get(f"{TMDB_BASE}/search/person", headers=HEADERS,
                         params={"query": name}).json()
        if r.get("results") and r["results"][0].get("profile_path"):
            return f"{POSTER_BASE}{r['results'][0]['profile_path']}"
        time.sleep(0.25)
    except:
        pass
    return None


def ensure_movie(conn, title, year_hint=None):
    """Find or create movie, return mediaid."""
    rows = conn.run("SELECT mediaid FROM media WHERE title=:t", t=title)
    if rows:
        return rows[0][0]
    # Try fuzzy
    rows = conn.run("SELECT mediaid FROM media WHERE title ILIKE :t", t=f"%{title}%")
    if rows:
        return rows[0][0]
    # Import from TMDB
    poster, rd, rating, runtime = tmdb_search_movie(title)
    if not rd and year_hint:
        rd = f"{year_hint}-01-01"
    conn.run("INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'movie');",
             t=title, r=rd, p=poster, a=rating)
    mid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
    conn.run("INSERT INTO movie (movieid, durationmin) VALUES (:id, :d);", id=mid, d=runtime)
    print(f"    + Imported movie: {title}")
    return mid


def ensure_series(conn, title):
    """Find or create series for Emmys, return mediaid."""
    rows = conn.run("SELECT mediaid FROM media WHERE title ILIKE :t", t=title)
    if rows:
        return rows[0][0]
    rows = conn.run("SELECT mediaid FROM media WHERE title ILIKE :t", t=f"%{title}%")
    if rows:
        return rows[0][0]
    poster, rd, rating = tmdb_search_tv(title)
    conn.run("INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, :a, 'series');",
             t=title, r=rd, p=poster, a=rating)
    mid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
    conn.run("INSERT INTO series (seriesid, status) VALUES (:id, 'Ended');", id=mid)
    print(f"    + Imported series: {title}")
    return mid


def ensure_person(conn, name):
    """Find or create person, return personid."""
    rows = conn.run("SELECT personid FROM person WHERE name=:n", n=name)
    if rows:
        return rows[0][0]
    photo = tmdb_search_person(name)
    conn.run("INSERT INTO person (name, photourl) VALUES (:n, :p);", n=name, p=photo)
    pid = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)[0][0]
    conn.run("INSERT INTO actor (actorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=pid)
    return pid


def add_media_nom(conn, event_id, cat_id, year, title, is_winner, year_hint=None):
    mid = ensure_movie(conn, title, year_hint)
    conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e, :c, :y, :w);",
             e=event_id, c=cat_id, y=year, w=is_winner)
    nom_id = conn.run("SELECT LASTVAL();")[0][0]
    conn.run("INSERT INTO media_nom (nomid, mediaid) VALUES (:n, :m);", n=nom_id, m=mid)


def add_series_nom(conn, event_id, cat_id, year, title, is_winner):
    mid = ensure_series(conn, title)
    conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e, :c, :y, :w);",
             e=event_id, c=cat_id, y=year, w=is_winner)
    nom_id = conn.run("SELECT LASTVAL();")[0][0]
    conn.run("INSERT INTO media_nom (nomid, mediaid) VALUES (:n, :m);", n=nom_id, m=mid)


def add_person_nom(conn, event_id, cat_id, year, name, subtitle, is_winner):
    pid = ensure_person(conn, name)
    conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e, :c, :y, :w);",
             e=event_id, c=cat_id, y=year, w=is_winner)
    nom_id = conn.run("SELECT LASTVAL();")[0][0]
    conn.run("INSERT INTO person_nom (nomid, personid) VALUES (:n, :p);", n=nom_id, p=pid)


def main():
    conn = get_db()
    try:
        print("🏆 Complete Awards Data Rebuild")
        print("=" * 60)

        # ══════════════════════════════════════════
        # CLEAR ALL existing award data
        # ══════════════════════════════════════════
        print("\n═══ Clearing old data ═══")
        conn.run("DELETE FROM media_nom;")
        conn.run("DELETE FROM person_nom;")
        conn.run("DELETE FROM nomination;")
        conn.run("DELETE FROM award_category;")
        conn.run("DELETE FROM award_event;")
        conn.run("SELECT setval(pg_get_serial_sequence('award_event','eventid'), 1, false);")
        conn.run("SELECT setval(pg_get_serial_sequence('award_category','categoryid'), 1, false);")
        conn.run("SELECT setval(pg_get_serial_sequence('nomination','nominationid'), 1, false);")
        print("  ✓ Cleared")

        # ══════════════════════════════════════════
        # CREATE EVENTS
        # ══════════════════════════════════════════
        print("\n═══ Creating events ═══")
        events = {
            "Academy Awards (Oscars)": "https://image.tmdb.org/t/p/original/gDEzVOofLDjafQXobCbIGglaykh.jpg",
            "Golden Globes": "https://image.tmdb.org/t/p/original/xGxRKJQdpReKzFubqPBLMdib6oO.jpg",
            "BAFTA Film Awards": "https://upload.wikimedia.org/wikipedia/en/thumb/5/5f/BAFTA_Award.png/200px-BAFTA_Award.png",
            "Cannes Film Festival": "https://image.tmdb.org/t/p/original/9byvBWN80gXVslNxfkrw6rQiCmS.jpg",
            "Emmy Awards": "https://image.tmdb.org/t/p/original/tVVkAkbqxfZEufwXHddnIAqiL1S.jpg",
        }
        ev = {}
        for name, img in events.items():
            conn.run("INSERT INTO award_event (name, imageurl) VALUES (:n, :i);", n=name, i=img)
            ev[name] = conn.run("SELECT eventid FROM award_event WHERE name=:n;", n=name)[0][0]
            print(f"  ✓ {name}")

        # ══════════════════════════════════════════
        # CREATE CATEGORIES
        # ══════════════════════════════════════════
        print("\n═══ Creating categories ═══")
        categories = [
            "Best Picture", "Best Actor", "Best Actress",
            "Best Supporting Actor", "Best Supporting Actress",
            "Best Director", "Best Animated Feature",
            "Best Film - Comedy/Musical",
            "Best Drama Series", "Best Comedy Series", "Best Limited Series",
        ]
        cat = {}
        for c in categories:
            conn.run("INSERT INTO award_category (name) VALUES (:n);", n=c)
            cat[c] = conn.run("SELECT categoryid FROM award_category WHERE name=:n;", n=c)[0][0]
            print(f"  ✓ {c}")

        O = ev["Academy Awards (Oscars)"]
        GG = ev["Golden Globes"]
        B = ev["BAFTA Film Awards"]
        C = ev["Cannes Film Festival"]
        E = ev["Emmy Awards"]
        BP = cat["Best Picture"]
        BA = cat["Best Actor"]
        BAC = cat["Best Actress"]
        BSA = cat["Best Supporting Actor"]
        BSAC = cat["Best Supporting Actress"]
        BD = cat["Best Director"]
        BAF = cat["Best Animated Feature"]
        BFCM = cat["Best Film - Comedy/Musical"]
        BDS = cat["Best Drama Series"]
        BCS = cat["Best Comedy Series"]
        BLS = cat["Best Limited Series"]

        # ══════════════════════════════════════════════════════════════
        #  OSCARS
        # ══════════════════════════════════════════════════════════════
        print("\n═══ OSCARS ═══")

        # --- 2026 (98th) ---
        print("  2026...")
        for t, w in [("One Battle After Another",True),("Bugonia",False),("F1",False),
                      ("Frankenstein",False),("Hamnet",False),("Marty Supreme",False),
                      ("The Secret Agent",False),("Sentimental Value",False),
                      ("Sinners",False),("Train Dreams",False)]:
            add_media_nom(conn, O, BP, 2026, t, w, 2026)

        for n, s, w in [("Michael B. Jordan","Sinners",True),("Timothée Chalamet","Marty Supreme",False),
                         ("Leonardo DiCaprio","One Battle After Another",False),
                         ("Ethan Hawke","Blue Moon",False),("Wagner Moura","The Secret Agent",False)]:
            add_person_nom(conn, O, BA, 2026, n, s, w)

        for n, s, w in [("Jessie Buckley","Hamnet",True),("Rose Byrne","If I Had Legs I'd Kick You",False),
                         ("Kate Hudson","Song Sung Blue",False),("Renate Reinsve","Sentimental Value",False),
                         ("Emma Stone","Bugonia",False)]:
            add_person_nom(conn, O, BAC, 2026, n, s, w)

        for n, s, w in [("Sean Penn","One Battle After Another",True),("Benicio del Toro","",False),
                         ("Jacob Elordi","",False),("Delroy Lindo","",False),("Stellan Skarsgård","",False)]:
            add_person_nom(conn, O, BSA, 2026, n, s, w)

        for n, s, w in [("Amy Madigan","Weapons",True),("Elle Fanning","",False),
                         ("Wunmi Mosaku","",False),("Teyana Taylor","",False),
                         ("Inga Ibsdotter Lilleaas","",False)]:
            add_person_nom(conn, O, BSAC, 2026, n, s, w)

        for t, w in [("KPop Demon Hunters",True),("Arco",False),("Elio",False),
                      ("Little Amélie or the Character of Rain",False),("Zootopia 2",False)]:
            add_media_nom(conn, O, BAF, 2026, t, w, 2026)
        print("    ✓ done")

        # --- 2025 (97th) ---
        print("  2025...")
        for t, w in [("Anora",True),("The Brutalist",False),("A Complete Unknown",False),
                      ("Conclave",False),("Dune: Part Two",False),("Emilia Pérez",False),
                      ("I'm Still Here",False),("Nickel Boys",False),
                      ("The Substance",False),("Wicked",False)]:
            add_media_nom(conn, O, BP, 2025, t, w, 2025)

        for n, s, w in [("Adrien Brody","The Brutalist",True),("Timothée Chalamet","A Complete Unknown",False),
                         ("Colman Domingo","Sing Sing",False),("Ralph Fiennes","Conclave",False),
                         ("Sebastian Stan","The Apprentice",False)]:
            add_person_nom(conn, O, BA, 2025, n, s, w)

        for n, s, w in [("Mikey Madison","Anora",True),("Cynthia Erivo","Wicked",False),
                         ("Karla Sofía Gascón","Emilia Pérez",False),("Demi Moore","The Substance",False),
                         ("Fernanda Torres","I'm Still Here",False)]:
            add_person_nom(conn, O, BAC, 2025, n, s, w)

        for n, s, w in [("Kieran Culkin","A Real Pain",True),("Yura Borisov","Anora",False),
                         ("Edward Norton","A Complete Unknown",False),("Guy Pearce","The Brutalist",False),
                         ("Jeremy Strong","The Apprentice",False)]:
            add_person_nom(conn, O, BSA, 2025, n, s, w)

        for n, s, w in [("Zoe Saldaña","Emilia Pérez",True),("Monica Barbaro","A Complete Unknown",False),
                         ("Ariana Grande","Wicked",False),("Felicity Jones","The Brutalist",False),
                         ("Isabella Rossellini","Conclave",False)]:
            add_person_nom(conn, O, BSAC, 2025, n, s, w)

        for t, w in [("Flow",True),("Inside Out 2",False),("Memoir of a Snail",False),
                      ("Wallace & Gromit: Vengeance Most Fowl",False),("The Wild Robot",False)]:
            add_media_nom(conn, O, BAF, 2025, t, w, 2025)
        print("    ✓ done")

        # --- 2024 (96th) ---
        print("  2024...")
        for t, w in [("Oppenheimer",True),("Barbie",False),("Poor Things",False),
                      ("Killers of the Flower Moon",False),("The Holdovers",False),
                      ("Maestro",False),("American Fiction",False),("Past Lives",False),
                      ("Anatomy of a Fall",False),("The Zone of Interest",False)]:
            add_media_nom(conn, O, BP, 2024, t, w, 2024)

        for n, s, w in [("Cillian Murphy","Oppenheimer",True),("Bradley Cooper","Maestro",False),
                         ("Colman Domingo","Rustin",False),("Paul Giamatti","The Holdovers",False),
                         ("Jeffrey Wright","American Fiction",False)]:
            add_person_nom(conn, O, BA, 2024, n, s, w)

        for n, s, w in [("Emma Stone","Poor Things",True),("Lily Gladstone","Killers of the Flower Moon",False),
                         ("Sandra Hüller","Anatomy of a Fall",False),("Carey Mulligan","Maestro",False),
                         ("Annette Bening","Nyad",False)]:
            add_person_nom(conn, O, BAC, 2024, n, s, w)

        for n, s, w in [("Robert Downey Jr.","Oppenheimer",True),("Ryan Gosling","Barbie",False),
                         ("Robert De Niro","Killers of the Flower Moon",False),
                         ("Mark Ruffalo","Poor Things",False),("Sterling K. Brown","American Fiction",False)]:
            add_person_nom(conn, O, BSA, 2024, n, s, w)

        for n, s, w in [("Da'Vine Joy Randolph","The Holdovers",True),("Emily Blunt","Oppenheimer",False),
                         ("Danielle Brooks","The Color Purple",False),("America Ferrera","Barbie",False),
                         ("Jodie Foster","Nyad",False)]:
            add_person_nom(conn, O, BSAC, 2024, n, s, w)

        for t, w in [("The Boy and the Heron",True),("Spider-Man: Across the Spider-Verse",False),
                      ("Elemental",False),("Nimona",False),("Robot Dreams",False)]:
            add_media_nom(conn, O, BAF, 2024, t, w, 2024)
        print("    ✓ done")

        # ══════════════════════════════════════════════════════════════
        #  BAFTA
        # ══════════════════════════════════════════════════════════════
        print("\n═══ BAFTA ═══")

        # --- 2026 ---
        print("  2026...")
        for t, w in [("Conclave",True),("Anora",False),("The Brutalist",False),
                      ("Emilia Pérez",False),("Wicked",False)]:
            add_media_nom(conn, B, BP, 2026, t, w)

        for n, s, w in [("Adrien Brody","The Brutalist",True),("Timothée Chalamet","",False),
                         ("Colman Domingo","",False),("Ralph Fiennes","",False),("Sebastian Stan","",False)]:
            add_person_nom(conn, B, BA, 2026, n, s, w)

        for n, s, w in [("Mikey Madison","Anora",True),("Cynthia Erivo","",False),
                         ("Karla Sofía Gascón","",False),("Demi Moore","",False),("Emma Stone","",False)]:
            add_person_nom(conn, B, BAC, 2026, n, s, w)

        for n, s, w in [("Kieran Culkin","",True),("Robert Downey Jr.","",False),
                         ("Ryan Gosling","",False),("Mark Ruffalo","",False),("Paul Mescal","",False)]:
            add_person_nom(conn, B, BSA, 2026, n, s, w)

        for n, s, w in [("Zoe Saldaña","",True),("Ariana Grande","",False),
                         ("Felicity Jones","",False),("Emily Blunt","",False),("Danielle Brooks","",False)]:
            add_person_nom(conn, B, BSAC, 2026, n, s, w)

        for t, w in [("The Boy and the Heron",True),("Spider-Man: Across the Spider-Verse",False),
                      ("Chicken Run: Dawn of the Nugget",False),("Elemental",False)]:
            add_media_nom(conn, B, BAF, 2026, t, w)
        print("    ✓ done")

        # --- 2025 ---
        print("  2025...")
        for t, w in [("Conclave",True),("Anora",False),("The Brutalist",False),
                      ("Emilia Pérez",False),("Wicked",False)]:
            add_media_nom(conn, B, BP, 2025, t, w)
        print("    ✓ done")

        # --- 2024 ---
        print("  2024...")
        for t, w in [("Oppenheimer",True),("Poor Things",False),("Killers of the Flower Moon",False),
                      ("The Holdovers",False),("Anatomy of a Fall",False)]:
            add_media_nom(conn, B, BP, 2024, t, w)
        print("    ✓ done")

        # ══════════════════════════════════════════════════════════════
        #  GOLDEN GLOBES
        # ══════════════════════════════════════════════════════════════
        print("\n═══ GOLDEN GLOBES ═══")

        # --- 2026 ---
        print("  2026...")
        for t, w in [("Hamnet",True),("Frankenstein",False),("The Secret Agent",False),
                      ("Sinners",False),("Sentimental Value",False)]:
            add_media_nom(conn, GG, BP, 2026, t, w, 2026)

        for t, w in [("One Battle After Another",True),("Bugonia",False),("Marty Supreme",False),
                      ("F1",False),("Train Dreams",False)]:
            add_media_nom(conn, GG, BFCM, 2026, t, w, 2026)

        for n, s, w in [("Wagner Moura","",True),("Leonardo DiCaprio","",False),
                         ("Ethan Hawke","",False),("Colman Domingo","",False),("Ralph Fiennes","",False)]:
            add_person_nom(conn, GG, BA, 2026, n, s, w)

        for n, s, w in [("Jessie Buckley","",True),("Emma Stone","",False),
                         ("Renate Reinsve","",False),("Kate Hudson","",False),("Carey Mulligan","",False)]:
            add_person_nom(conn, GG, BAC, 2026, n, s, w)

        for n, s, w in [("Stellan Skarsgård","",True),("Robert Downey Jr.","",False),
                         ("Ryan Gosling","",False),("Mark Ruffalo","",False),("Paul Mescal","",False)]:
            add_person_nom(conn, GG, BSA, 2026, n, s, w)

        for n, s, w in [("Teyana Taylor","",True),("Zoe Saldaña","",False),
                         ("Ariana Grande","",False),("Emily Blunt","",False),("Danielle Brooks","",False)]:
            add_person_nom(conn, GG, BSAC, 2026, n, s, w)

        for t, w in [("KPop Demon Hunters",True),("Elio",False),("Zootopia 2",False),
                      ("Arco",False),("Little Amélie or the Character of Rain",False)]:
            add_media_nom(conn, GG, BAF, 2026, t, w, 2026)
        print("    ✓ done")

        # --- 2025 ---
        print("  2025...")
        for t, w in [("The Brutalist",True),("Anora",False),("Wicked",False),
                      ("Dune: Part Two",False),("Conclave",False)]:
            add_media_nom(conn, GG, BP, 2025, t, w)

        for t, w in [("Emilia Pérez",True)]:
            add_media_nom(conn, GG, BFCM, 2025, t, w)
        print("    ✓ done")

        # --- 2024 ---
        print("  2024...")
        for t, w in [("Oppenheimer",True)]:
            add_media_nom(conn, GG, BP, 2024, t, w)
        for t, w in [("Poor Things",True)]:
            add_media_nom(conn, GG, BFCM, 2024, t, w)
        print("    ✓ done")

        # ══════════════════════════════════════════════════════════════
        #  CANNES
        # ══════════════════════════════════════════════════════════════
        print("\n═══ CANNES ═══")

        # --- 2026 ---
        print("  2026...")
        for t, w in [("The Secret Agent",True),("Hamnet",False),("Sentimental Value",False),
                      ("Sinners",False),("Bugonia",False),("Frankenstein",False)]:
            add_media_nom(conn, C, BP, 2026, t, w, 2026)
        print("    ✓ done")

        # --- 2025 ---
        print("  2025...")
        for t, w in [("Anora",True),("The Apprentice",False),("Megalopolis",False),
                      ("Emilia Pérez",False),("Kinds of Kindness",False)]:
            add_media_nom(conn, C, BP, 2025, t, w, 2025)
        print("    ✓ done")

        # --- 2024 ---
        print("  2024...")
        for t, w in [("Anatomy of a Fall",True),("The Zone of Interest",False),
                      ("Perfect Days",False),("Monster",False),("Asteroid City",False)]:
            add_media_nom(conn, C, BP, 2024, t, w, 2024)
        print("    ✓ done")

        # ══════════════════════════════════════════════════════════════
        #  EMMYS
        # ══════════════════════════════════════════════════════════════
        print("\n═══ EMMYS ═══")

        # --- 2026 ---
        print("  2026...")
        for t, w in [("Shōgun",True),("Succession",False),("The Last of Us",False),
                      ("The Crown",False),("House of the Dragon",False)]:
            add_series_nom(conn, E, BDS, 2026, t, w)

        for t, w in [("The Bear",True),("Abbott Elementary",False),
                      ("Only Murders in the Building",False),("Ted Lasso",False)]:
            add_series_nom(conn, E, BCS, 2026, t, w)

        for t, w in [("Baby Reindeer",True),("Beef",False),("Dahmer",False),("Ripley",False)]:
            add_series_nom(conn, E, BLS, 2026, t, w)
        print("    ✓ done")

        # --- 2025 ---
        print("  2025...")
        for t, w in [("Succession",True)]:
            add_series_nom(conn, E, BDS, 2025, t, w)
        for t, w in [("The Bear",True)]:
            add_series_nom(conn, E, BCS, 2025, t, w)
        print("    ✓ done")

        # --- 2024 ---
        print("  2024...")
        for t, w in [("Succession",True)]:
            add_series_nom(conn, E, BDS, 2024, t, w)
        for t, w in [("The Bear",True)]:
            add_series_nom(conn, E, BCS, 2024, t, w)
        print("    ✓ done")

        # ══════════════════════════════════════════════════════════════
        #  FINAL STATS
        # ══════════════════════════════════════════════════════════════
        total = conn.run("SELECT COUNT(*) FROM nomination")[0][0]
        winners = conn.run("SELECT COUNT(*) FROM nomination WHERE iswinner=TRUE")[0][0]
        events_count = conn.run("SELECT COUNT(*) FROM award_event")[0][0]
        cats_count = conn.run("SELECT COUNT(*) FROM award_category")[0][0]
        print(f"\n📊 Final: {events_count} events, {cats_count} categories, {total} nominations, {winners} winners")
        print("\n✅ Awards rebuild complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
