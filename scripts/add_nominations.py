"""
Adds award nominations by hand, for anything import_awards doesn't cover.

Fill in the lists below with ids from our database (the number in a page's
URL, e.g. /movie.html?id=161) and run:

    python -m scripts.add_nominations
"""
from database import get_db

EVENT = "Academy Awards (Oscars)"     # must match a row in award_event
YEAR = 2024                           # ceremony year

# (media id, category, won?)
MEDIA_NOMINEES = [
    # (161, "Best Picture", True),
]

# (person id, category, what they were nominated for, won?)
PERSON_NOMINEES = [
    # (707, "Best Actor", "Oppenheimer", True),
]


def category_id(conn, name):
    rows = conn.run("SELECT categoryid FROM award_category WHERE name = :n;", n=name)
    if rows:
        return rows[0][0]
    return conn.run("INSERT INTO award_category (name) VALUES (:n) RETURNING categoryid;", n=name)[0][0]


def nominate(conn, event_id, category, won):
    return conn.run(
        """INSERT INTO nomination (eventid, categoryid, year, iswinner)
           VALUES (:e, :c, :y, :w) RETURNING nominationid;""",
        e=event_id, c=category_id(conn, category), y=YEAR, w=won)[0][0]


def main():
    if not MEDIA_NOMINEES and not PERSON_NOMINEES:
        print("Nothing to add - fill in MEDIA_NOMINEES / PERSON_NOMINEES first.")
        return
    conn = get_db()
    try:
        event = conn.run("SELECT eventid FROM award_event WHERE name = :n;", n=EVENT)
        if not event:
            print(f"No award event called {EVENT!r}")
            return
        conn.run("BEGIN")
        for mediaid, category, won in MEDIA_NOMINEES:
            nomid = nominate(conn, event[0][0], category, won)
            conn.run("INSERT INTO media_nom (nomid, mediaid) VALUES (:n, :m);", n=nomid, m=mediaid)
            print(f"  media #{mediaid} -> {category}{' (winner)' if won else ''}")
        for personid, category, subtitle, won in PERSON_NOMINEES:
            nomid = nominate(conn, event[0][0], category, won)
            conn.run("INSERT INTO person_nom (nomid, personid, subtitle) VALUES (:n, :p, :s);",
                     n=nomid, p=personid, s=subtitle)
            print(f"  person #{personid} -> {category}{' (winner)' if won else ''}")
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
