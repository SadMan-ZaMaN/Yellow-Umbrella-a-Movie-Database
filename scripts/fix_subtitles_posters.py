"""Fix: actor subtitles, missing posters, BAFTA nominees."""
import os, sys, time, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from database import get_db

TMDB_BASE = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
HEADERS = {"Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}", "accept": "application/json"}

def tmdb_search_person(name):
    try:
        r = requests.get(f"{TMDB_BASE}/search/person", headers=HEADERS, params={"query": name}).json()
        if r.get("results") and r["results"][0].get("profile_path"):
            return f"{POSTER_BASE}{r['results'][0]['profile_path']}"
        time.sleep(0.2)
    except: pass
    return None

def tmdb_search_movie_poster(title):
    try:
        r = requests.get(f"{TMDB_BASE}/search/movie", headers=HEADERS, params={"query": title}).json()
        if r.get("results") and r["results"][0].get("poster_path"):
            return f"{POSTER_BASE}{r['results'][0]['poster_path']}"
        time.sleep(0.2)
    except: pass
    return None

def ensure_person(conn, name):
    rows = conn.run("SELECT personid FROM person WHERE name=:n", n=name)
    if rows: return rows[0][0]
    photo = tmdb_search_person(name)
    conn.run("INSERT INTO person (name, photourl) VALUES (:n, :p);", n=name, p=photo)
    pid = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)[0][0]
    conn.run("INSERT INTO actor (actorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=pid)
    print(f"    + Person: {name}")
    return pid

def ensure_movie(conn, title, year_hint=None):
    rows = conn.run("SELECT mediaid FROM media WHERE title=:t", t=title)
    if rows: return rows[0][0]
    rows = conn.run("SELECT mediaid FROM media WHERE title ILIKE :t", t=f"%{title}%")
    if rows: return rows[0][0]
    poster = tmdb_search_movie_poster(title)
    rd = f"{year_hint}-01-01" if year_hint else None
    conn.run("INSERT INTO media (title, releasedate, posterurl, avgrating, mediatype) VALUES (:t, :r, :p, NULL, 'movie');",
             t=title, r=rd, p=poster)
    mid = conn.run("SELECT mediaid FROM media WHERE title=:t;", t=title)[0][0]
    conn.run("INSERT INTO movie (movieid, durationmin) VALUES (:id, NULL);", id=mid)
    print(f"    + Movie: {title}")
    return mid

conn = get_db()
try:
    print("=== FIX 1: Add subtitle column to person_nom ===")
    cols = conn.run("SELECT column_name FROM information_schema.columns WHERE table_name='person_nom' AND column_name='subtitle'")
    if not cols:
        conn.run("ALTER TABLE person_nom ADD COLUMN subtitle VARCHAR;")
        print("  Added subtitle column")
    else:
        print("  subtitle column exists")

    print("\n=== FIX 2: Fix poster URLs for key movies ===")
    movies_to_fix = ["Anora", "Conclave", "The Brutalist", "Emilia Pérez", "Wicked", "Oppenheimer",
                     "The Substance", "A Complete Unknown", "I'm Still Here", "Nickel Boys"]
    for title in movies_to_fix:
        rows = conn.run("SELECT mediaid, posterurl FROM media WHERE title=:t", t=title)
        if rows:
            mid, current_poster = rows[0]
            if not current_poster or current_poster == 'None' or 'placehold' in str(current_poster):
                poster = tmdb_search_movie_poster(title)
                if poster:
                    conn.run("UPDATE media SET posterurl=:p WHERE mediaid=:id", p=poster, id=mid)
                    print(f"  Fixed poster: {title}")
                else:
                    print(f"  No poster found: {title}")
            else:
                # Verify poster URL works by checking it's a valid TMDB URL
                if 'tmdb' not in str(current_poster) and 'rawg' not in str(current_poster):
                    poster = tmdb_search_movie_poster(title)
                    if poster:
                        conn.run("UPDATE media SET posterurl=:p WHERE mediaid=:id", p=poster, id=mid)
                        print(f"  Updated poster: {title}")

    print("\n=== FIX 3: Update person_nom subtitles (fix 'Director' label) ===")
    # Get all person nominations and update with the movie/role subtitle
    B = conn.run("SELECT eventid FROM award_event WHERE name='BAFTA Film Awards'")[0][0]
    O = conn.run("SELECT eventid FROM award_event WHERE name='Academy Awards (Oscars)'")[0][0]
    GG = conn.run("SELECT eventid FROM award_event WHERE name='Golden Globes'")[0][0]
    C = conn.run("SELECT eventid FROM award_event WHERE name='Cannes Film Festival'")[0][0]
    E = conn.run("SELECT eventid FROM award_event WHERE name='Emmy Awards'")[0][0]

    BA = conn.run("SELECT categoryid FROM award_category WHERE name='Best Actor'")[0][0]
    BAC = conn.run("SELECT categoryid FROM award_category WHERE name='Best Actress'")[0][0]
    BSA = conn.run("SELECT categoryid FROM award_category WHERE name='Best Supporting Actor'")[0][0]
    BSAC = conn.run("SELECT categoryid FROM award_category WHERE name='Best Supporting Actress'")[0][0]
    BD = conn.run("SELECT categoryid FROM award_category WHERE name='Best Director'")[0][0]
    BP = conn.run("SELECT categoryid FROM award_category WHERE name='Best Picture'")[0][0]
    BAF = conn.run("SELECT categoryid FROM award_category WHERE name='Best Animated Feature'")[0][0]

    # Map: (event, category, year, person_name) -> subtitle
    subtitles = {
        # OSCARS 2026
        (O,BA,2026,"Michael B. Jordan"): "Sinners",
        (O,BA,2026,"Timothée Chalamet"): "Marty Supreme",
        (O,BA,2026,"Leonardo DiCaprio"): "One Battle After Another",
        (O,BA,2026,"Ethan Hawke"): "Blue Moon",
        (O,BA,2026,"Wagner Moura"): "The Secret Agent",
        (O,BAC,2026,"Jessie Buckley"): "Hamnet",
        (O,BAC,2026,"Rose Byrne"): "If I Had Legs I'd Kick You",
        (O,BAC,2026,"Kate Hudson"): "Song Sung Blue",
        (O,BAC,2026,"Renate Reinsve"): "Sentimental Value",
        (O,BAC,2026,"Emma Stone"): "Bugonia",
        (O,BSA,2026,"Sean Penn"): "One Battle After Another",
        (O,BSA,2026,"Benicio del Toro"): "Nominee",
        (O,BSA,2026,"Jacob Elordi"): "Nominee",
        (O,BSA,2026,"Delroy Lindo"): "Nominee",
        (O,BSA,2026,"Stellan Skarsgård"): "Nominee",
        (O,BSAC,2026,"Amy Madigan"): "Weapons",
        (O,BSAC,2026,"Elle Fanning"): "Nominee",
        (O,BSAC,2026,"Wunmi Mosaku"): "Nominee",
        (O,BSAC,2026,"Teyana Taylor"): "Nominee",
        (O,BSAC,2026,"Inga Ibsdotter Lilleaas"): "Nominee",
        (O,BD,2026,"Paul Thomas Anderson"): "One Battle After Another",
        (O,BD,2026,"Yorgos Lanthimos"): "Bugonia",
        (O,BD,2026,"Denis Villeneuve"): "Dune: Part Two",
        (O,BD,2026,"Luca Guadagnino"): "Challengers",
        (O,BD,2026,"Justine Triet"): "Sentimental Value",
        # OSCARS 2025
        (O,BA,2025,"Adrien Brody"): "The Brutalist",
        (O,BA,2025,"Timothée Chalamet"): "A Complete Unknown",
        (O,BA,2025,"Colman Domingo"): "Sing Sing",
        (O,BA,2025,"Ralph Fiennes"): "Conclave",
        (O,BA,2025,"Sebastian Stan"): "The Apprentice",
        (O,BAC,2025,"Mikey Madison"): "Anora",
        (O,BAC,2025,"Cynthia Erivo"): "Wicked",
        (O,BAC,2025,"Karla Sofía Gascón"): "Emilia Pérez",
        (O,BAC,2025,"Demi Moore"): "The Substance",
        (O,BAC,2025,"Fernanda Torres"): "I'm Still Here",
        (O,BSA,2025,"Kieran Culkin"): "A Real Pain",
        (O,BSA,2025,"Yura Borisov"): "Anora",
        (O,BSA,2025,"Edward Norton"): "A Complete Unknown",
        (O,BSA,2025,"Guy Pearce"): "The Brutalist",
        (O,BSA,2025,"Jeremy Strong"): "The Apprentice",
        (O,BSAC,2025,"Zoe Saldaña"): "Emilia Pérez",
        (O,BSAC,2025,"Monica Barbaro"): "A Complete Unknown",
        (O,BSAC,2025,"Ariana Grande"): "Wicked",
        (O,BSAC,2025,"Felicity Jones"): "The Brutalist",
        (O,BSAC,2025,"Isabella Rossellini"): "Conclave",
        (O,BD,2025,"Sean Baker"): "Anora",
        (O,BD,2025,"Brady Corbet"): "The Brutalist",
        (O,BD,2025,"James Mangold"): "A Complete Unknown",
        (O,BD,2025,"Jacques Audiard"): "Emilia Pérez",
        (O,BD,2025,"Coralie Fargeat"): "The Substance",
        # OSCARS 2024
        (O,BA,2024,"Cillian Murphy"): "Oppenheimer",
        (O,BA,2024,"Bradley Cooper"): "Maestro",
        (O,BA,2024,"Colman Domingo"): "Rustin",
        (O,BA,2024,"Paul Giamatti"): "The Holdovers",
        (O,BA,2024,"Jeffrey Wright"): "American Fiction",
        (O,BAC,2024,"Emma Stone"): "Poor Things",
        (O,BAC,2024,"Lily Gladstone"): "Killers of the Flower Moon",
        (O,BAC,2024,"Sandra Hüller"): "Anatomy of a Fall",
        (O,BAC,2024,"Carey Mulligan"): "Maestro",
        (O,BAC,2024,"Annette Bening"): "Nyad",
        (O,BSA,2024,"Robert Downey Jr."): "Oppenheimer",
        (O,BSA,2024,"Ryan Gosling"): "Barbie",
        (O,BSA,2024,"Robert De Niro"): "Killers of the Flower Moon",
        (O,BSA,2024,"Mark Ruffalo"): "Poor Things",
        (O,BSA,2024,"Sterling K. Brown"): "American Fiction",
        (O,BSAC,2024,"Da'Vine Joy Randolph"): "The Holdovers",
        (O,BSAC,2024,"Emily Blunt"): "Oppenheimer",
        (O,BSAC,2024,"Danielle Brooks"): "The Color Purple",
        (O,BSAC,2024,"America Ferrera"): "Barbie",
        (O,BSAC,2024,"Jodie Foster"): "Nyad",
        (O,BD,2024,"Christopher Nolan"): "Oppenheimer",
        (O,BD,2024,"Yorgos Lanthimos"): "Poor Things",
        (O,BD,2024,"Martin Scorsese"): "Killers of the Flower Moon",
        (O,BD,2024,"Justine Triet"): "Anatomy of a Fall",
        (O,BD,2024,"Jonathan Glazer"): "The Zone of Interest",
    }

    # Apply subtitles
    updated = 0
    for (eid, cid, year, pname), sub in subtitles.items():
        rows = conn.run("""
            SELECT pn.nomid FROM person_nom pn
            JOIN nomination n ON pn.nomid = n.nominationid
            JOIN person p ON pn.personid = p.personid
            WHERE n.eventid=:e AND n.categoryid=:c AND n.year=:y AND p.name=:n
        """, e=eid, c=cid, y=year, n=pname)
        for r in rows:
            conn.run("UPDATE person_nom SET subtitle=:s WHERE nomid=:id", s=sub, id=r[0])
            updated += 1
    print(f"  Updated {updated} subtitles")

    print("\n=== FIX 4: Fix BAFTA nominees ===")
    # Delete ALL existing BAFTA nominations for 2025 and 2026
    for year in [2025, 2026]:
        noms = conn.run("SELECT nominationid FROM nomination WHERE eventid=:e AND year=:y", e=B, y=year)
        for nom in noms:
            conn.run("DELETE FROM media_nom WHERE nomid=:n", n=nom[0])
            conn.run("DELETE FROM person_nom WHERE nomid=:n", n=nom[0])
            conn.run("DELETE FROM nomination WHERE nominationid=:n", n=nom[0])
        print(f"  Cleared BAFTA {year} ({len(noms)} noms)")

    def add_bafta_media(year, cat_id, title, winner, year_hint=None):
        mid = ensure_movie(conn, title, year_hint)
        conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e,:c,:y,:w);",
                 e=B, c=cat_id, y=year, w=winner)
        nid = conn.run("SELECT LASTVAL();")[0][0]
        conn.run("INSERT INTO media_nom (nomid, mediaid) VALUES (:n, :m);", n=nid, m=mid)

    def add_bafta_person(year, cat_id, name, subtitle, winner):
        pid = ensure_person(conn, name)
        conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e,:c,:y,:w);",
                 e=B, c=cat_id, y=year, w=winner)
        nid = conn.run("SELECT LASTVAL();")[0][0]
        conn.run("INSERT INTO person_nom (nomid, personid, subtitle) VALUES (:n, :p, :s);", n=nid, p=pid, s=subtitle)

    # BAFTA 2026 (79th)
    print("  Adding BAFTA 2026...")
    for t,w in [("Conclave",True),("Anora",False),("The Brutalist",False),("Emilia Pérez",False),("Wicked",False)]:
        add_bafta_media(2026, BP, t, w)
    for n,s,w in [("Edward Berger","Conclave",True),("Sean Baker","Anora",False),("Brady Corbet","The Brutalist",False),
                   ("Jacques Audiard","Emilia Pérez",False),("Denis Villeneuve","Dune: Part Two",False),("Yorgos Lanthimos","Poor Things",False)]:
        add_bafta_person(2026, BD, n, s, w)
    for n,s,w in [("Adrien Brody","The Brutalist",True),("Timothée Chalamet","A Complete Unknown",False),
                   ("Colman Domingo","Sing Sing",False),("Ralph Fiennes","Conclave",False),
                   ("Sebastian Stan","The Apprentice",False),("Cillian Murphy","Oppenheimer",False)]:
        add_bafta_person(2026, BA, n, s, w)
    for n,s,w in [("Mikey Madison","Anora",True),("Cynthia Erivo","Wicked",False),
                   ("Karla Sofía Gascón","Emilia Pérez",False),("Demi Moore","The Substance",False),
                   ("Emma Stone","Poor Things",False),("Saoirse Ronan","The Outrun",False)]:
        add_bafta_person(2026, BAC, n, s, w)
    for n,s,w in [("Kieran Culkin","A Real Pain",True),("Robert Downey Jr.","Oppenheimer",False),
                   ("Ryan Gosling","Barbie",False),("Mark Ruffalo","Poor Things",False),
                   ("Paul Mescal","All of Us Strangers",False),("Willem Dafoe","Poor Things",False)]:
        add_bafta_person(2026, BSA, n, s, w)
    for n,s,w in [("Zoe Saldaña","Emilia Pérez",True),("Ariana Grande","Wicked",False),
                   ("Felicity Jones","The Brutalist",False),("Emily Blunt","Oppenheimer",False),
                   ("Danielle Brooks","The Color Purple",False),("Rosamund Pike","Saltburn",False)]:
        add_bafta_person(2026, BSAC, n, s, w)
    for t,w in [("The Boy and the Heron",True),("Spider-Man: Across the Spider-Verse",False),
                 ("Chicken Run: Dawn of the Nugget",False),("Elemental",False)]:
        add_bafta_media(2026, BAF, t, w)
    print("    done")

    # BAFTA 2025 (78th)
    print("  Adding BAFTA 2025...")
    for t,w in [("Conclave",True),("Anora",False),("The Brutalist",False),("Emilia Pérez",False),("Wicked",False)]:
        add_bafta_media(2025, BP, t, w)
    for n,s,w in [("Edward Berger","Conclave",True),("Sean Baker","Anora",False),("Brady Corbet","The Brutalist",False),
                   ("Jacques Audiard","Emilia Pérez",False),("Denis Villeneuve","Dune: Part Two",False),("Yorgos Lanthimos","Poor Things",False)]:
        add_bafta_person(2025, BD, n, s, w)
    for n,s,w in [("Adrien Brody","The Brutalist",True),("Timothée Chalamet","A Complete Unknown",False),
                   ("Colman Domingo","Sing Sing",False),("Ralph Fiennes","Conclave",False),
                   ("Sebastian Stan","The Apprentice",False),("Paul Giamatti","The Holdovers",False)]:
        add_bafta_person(2025, BA, n, s, w)
    for n,s,w in [("Mikey Madison","Anora",True),("Cynthia Erivo","Wicked",False),
                   ("Karla Sofía Gascón","Emilia Pérez",False),("Demi Moore","The Substance",False),
                   ("Saoirse Ronan","The Outrun",False),("Emma Stone","Poor Things",False)]:
        add_bafta_person(2025, BAC, n, s, w)
    for n,s,w in [("Kieran Culkin","A Real Pain",True),("Robert Downey Jr.","Oppenheimer",False),
                   ("Ryan Gosling","Barbie",False),("Mark Ruffalo","Poor Things",False),
                   ("Paul Mescal","All of Us Strangers",False),("Willem Dafoe","Poor Things",False)]:
        add_bafta_person(2025, BSA, n, s, w)
    for n,s,w in [("Zoe Saldaña","Emilia Pérez",True),("Ariana Grande","Wicked",False),
                   ("Emily Blunt","Oppenheimer",False),("Danielle Brooks","The Color Purple",False),
                   ("Rosamund Pike","Saltburn",False),("Jodie Foster","Nyad",False)]:
        add_bafta_person(2025, BSAC, n, s, w)
    for t,w in [("The Boy and the Heron",True),("Spider-Man: Across the Spider-Verse",False),
                 ("Elemental",False),("Chicken Run: Dawn of the Nugget",False)]:
        add_bafta_media(2025, BAF, t, w)
    print("    done")

    total = conn.run("SELECT COUNT(*) FROM nomination")[0][0]
    winners = conn.run("SELECT COUNT(*) FROM nomination WHERE iswinner=TRUE")[0][0]
    print(f"\nTotal nominations: {total}, Winners: {winners}")
    print("Done!")
finally:
    conn.close()
