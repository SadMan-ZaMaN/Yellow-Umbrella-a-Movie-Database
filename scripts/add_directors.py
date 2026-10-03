"""Add Best Director nominations to all events."""
import os, sys, time, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from database import get_db

TMDB_BASE = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
HEADERS = {"Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}", "accept": "application/json"}

def ensure_person(conn, name):
    rows = conn.run("SELECT personid FROM person WHERE name=:n", n=name)
    if rows: return rows[0][0]
    try:
        r = requests.get(f"{TMDB_BASE}/search/person", headers=HEADERS, params={"query": name}).json()
        photo = f"{POSTER_BASE}{r['results'][0]['profile_path']}" if r.get("results") and r["results"][0].get("profile_path") else None
        time.sleep(0.2)
    except:
        photo = None
    conn.run("INSERT INTO person (name, photourl) VALUES (:n, :p);", n=name, p=photo)
    pid = conn.run("SELECT personid FROM person WHERE name=:n;", n=name)[0][0]
    conn.run("INSERT INTO director (directorid) VALUES (:id) ON CONFLICT DO NOTHING;", id=pid)
    print(f"    + Person: {name}")
    return pid

def add_dir(conn, ev, cat, year, name, subtitle, winner):
    pid = ensure_person(conn, name)
    conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e,:c,:y,:w);",
             e=ev, c=cat, y=year, w=winner)
    nid = conn.run("SELECT LASTVAL();")[0][0]
    conn.run("INSERT INTO person_nom (nomid, personid) VALUES (:n,:p);", n=nid, p=pid)

conn = get_db()
try:
    O = conn.run("SELECT eventid FROM award_event WHERE name='Academy Awards (Oscars)'")[0][0]
    GG = conn.run("SELECT eventid FROM award_event WHERE name='Golden Globes'")[0][0]
    B = conn.run("SELECT eventid FROM award_event WHERE name='BAFTA Film Awards'")[0][0]
    C = conn.run("SELECT eventid FROM award_event WHERE name='Cannes Film Festival'")[0][0]
    E = conn.run("SELECT eventid FROM award_event WHERE name='Emmy Awards'")[0][0]
    BD = conn.run("SELECT categoryid FROM award_category WHERE name='Best Director'")[0][0]

    print("Adding Best Director nominations...")

    # OSCARS
    print("\n  OSCARS 2026:")
    for n,s,w in [("Paul Thomas Anderson","One Battle After Another",True),
                   ("Yorgos Lanthimos","Bugonia",False),("Denis Villeneuve","Dune: Part Two",False),
                   ("Luca Guadagnino","Challengers",False),("Justine Triet","Sentimental Value",False)]:
        add_dir(conn, O, BD, 2026, n, s, w)
    print("    done")

    print("  OSCARS 2025:")
    for n,s,w in [("Sean Baker","Anora",True),("Brady Corbet","The Brutalist",False),
                   ("James Mangold","A Complete Unknown",False),("Jacques Audiard","Emilia Perez",False),
                   ("Coralie Fargeat","The Substance",False)]:
        add_dir(conn, O, BD, 2025, n, s, w)
    print("    done")

    print("  OSCARS 2024:")
    for n,s,w in [("Christopher Nolan","Oppenheimer",True),("Yorgos Lanthimos","Poor Things",False),
                   ("Martin Scorsese","Killers of the Flower Moon",False),
                   ("Justine Triet","Anatomy of a Fall",False),("Jonathan Glazer","The Zone of Interest",False)]:
        add_dir(conn, O, BD, 2024, n, s, w)
    print("    done")

    # BAFTA
    print("\n  BAFTA 2026:")
    for n,s,w in [("Edward Berger","Conclave",True),("Sean Baker","Anora",False),
                   ("Brady Corbet","The Brutalist",False),("Jacques Audiard","Emilia Perez",False),
                   ("Denis Villeneuve","Dune: Part Two",False),("Yorgos Lanthimos","Bugonia",False)]:
        add_dir(conn, B, BD, 2026, n, s, w)
    print("    done")

    print("  BAFTA 2025:")
    for n,s,w in [("Edward Berger","Conclave",True),("Christopher Nolan","Oppenheimer",False),
                   ("Yorgos Lanthimos","Poor Things",False),("Justine Triet","Anatomy of a Fall",False),
                   ("Jonathan Glazer","The Zone of Interest",False),("Alexander Payne","The Holdovers",False)]:
        add_dir(conn, B, BD, 2025, n, s, w)
    print("    done")

    print("  BAFTA 2024:")
    for n,s,w in [("Christopher Nolan","Oppenheimer",True),("Yorgos Lanthimos","Poor Things",False),
                   ("Martin Scorsese","Killers of the Flower Moon",False),
                   ("Justine Triet","Anatomy of a Fall",False),("Jonathan Glazer","The Zone of Interest",False),
                   ("Alexander Payne","The Holdovers",False)]:
        add_dir(conn, B, BD, 2024, n, s, w)
    print("    done")

    # GOLDEN GLOBES
    print("\n  GG 2026:")
    for n,s,w in [("Paul Thomas Anderson","One Battle After Another",True),
                   ("Yorgos Lanthimos","Bugonia",False),("Denis Villeneuve","",False),
                   ("Luca Guadagnino","",False),("Justine Triet","",False)]:
        add_dir(conn, GG, BD, 2026, n, s, w)
    print("    done")

    print("  GG 2025:")
    for n,s,w in [("Brady Corbet","The Brutalist",True),("Sean Baker","Anora",False),
                   ("Jacques Audiard","Emilia Perez",False),("James Mangold","A Complete Unknown",False),
                   ("Coralie Fargeat","The Substance",False)]:
        add_dir(conn, GG, BD, 2025, n, s, w)
    print("    done")

    print("  GG 2024:")
    for n,s,w in [("Christopher Nolan","Oppenheimer",True),("Martin Scorsese","Killers of the Flower Moon",False),
                   ("Yorgos Lanthimos","Poor Things",False),("Greta Gerwig","Barbie",False),
                   ("Bradley Cooper","Maestro",False)]:
        add_dir(conn, GG, BD, 2024, n, s, w)
    print("    done")

    # CANNES
    print("\n  CANNES 2026:")
    for n,s,w in [("Kleber Mendonca Filho","",True),("Paul Thomas Anderson","",False),
                   ("Yorgos Lanthimos","",False),("Luca Guadagnino","",False),
                   ("Jacques Audiard","",False),("Denis Villeneuve","",False)]:
        add_dir(conn, C, BD, 2026, n, s, w)
    print("    done")

    print("  CANNES 2025:")
    for n,s,w in [("Miguel Gomes","Grand Tour",True)]:
        add_dir(conn, C, BD, 2025, n, s, w)
    print("    done")

    print("  CANNES 2024:")
    for n,s,w in [("Tran Anh Hung","",True)]:
        add_dir(conn, C, BD, 2024, n, s, w)
    print("    done")

    # EMMYS
    print("\n  EMMYS 2026:")
    for n,s,w in [("Frederick E. O. Toye","Shogun",True),("Mark Mylod","Succession",False)]:
        add_dir(conn, E, BD, 2026, n, s, w)
    print("    done")

    print("  EMMYS 2025:")
    for n,s,w in [("Mark Mylod","Succession",True)]:
        add_dir(conn, E, BD, 2025, n, s, w)
    print("    done")

    print("  EMMYS 2024:")
    for n,s,w in [("Mark Mylod","Succession",True)]:
        add_dir(conn, E, BD, 2024, n, s, w)
    print("    done")

    total = conn.run("SELECT COUNT(*) FROM nomination")[0][0]
    winners = conn.run("SELECT COUNT(*) FROM nomination WHERE iswinner=TRUE")[0][0]
    dirs = conn.run("SELECT COUNT(*) FROM nomination WHERE categoryid=:c", c=BD)[0][0]
    print(f"\nBest Director noms added: {dirs}")
    print(f"Total nominations: {total}, Winners: {winners}")
    print("Done!")
finally:
    conn.close()
