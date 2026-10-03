from database import get_db

# =======================================================
# 🏆 BULK AWARDS SEEDER 🏆
# Put your IDs here and run `python -m scripts.add_nominations`
# =======================================================

# Which event to populate? 
# 1=Oscars, 2=Golden Globes, 3=BAFTA, 4=Cannes, 5=Emmy
EVENT_ID = 1
YEAR = 2024

# --- 🎬 MEDIA NOMINATIONS (Movies, Series, Anime, Games) ---
# Format: (Media ID, Category Name, Is Winner)
MEDIA_NOMINEES = [
    (173, "Best Picture", True),        # Example: Manchester Death Warrant (Wins)
    (175, "Best Picture", False),       # Example: It Was Showering In Manchest (Nominated)
    # Add your real IDs below:
    # (12345, "Best Original Score", False),
    # (67890, "Best Animated Feature", True),
]

# --- 🎭 PERSON NOMINATIONS (Actors, Directors) ---
# Format: (Person ID, Category Name, Is Winner)
PERSON_NOMINEES = [
    (312, "Best Actress", True),        # Example: Sky Katz (Wins)
    (129, "Best Supporting Actor", False), # Example: Maia Kealoha (Nominated)
    # Add your real IDs below:
    # (99999, "Best Director", True),
]

# =======================================================
# DO NOT EDIT BELOW THIS LINE
# =======================================================

def get_or_create_category(conn, category_name):
    # Ensure category exists and return its ID
    rows = conn.run("SELECT categoryid FROM award_category WHERE name = :n", n=category_name)
    if rows: return rows[0][0]
    
    conn.run("INSERT INTO award_category (name) VALUES (:n)", n=category_name)
    return conn.run("SELECT categoryid FROM award_category WHERE name = :n", n=category_name)[0][0]

def main():
    conn = get_db()
    try:
        conn.run("BEGIN")
        
        # Insert Media
        for media_id, cat_name, is_winner in MEDIA_NOMINEES:
            cat_id = get_or_create_category(conn, cat_name)
            conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e, :c, :y, :w)", 
                     e=EVENT_ID, c=cat_id, y=YEAR, w=is_winner)
            nom_id = conn.run("SELECT MAX(nominationid) FROM nomination")[0][0]
            conn.run("INSERT INTO media_nom (nomid, mediaid) VALUES (:n, :m)", n=nom_id, m=media_id)
            print(f"🎬 Added Media ID {media_id} -> {cat_name} ({'Winner' if is_winner else 'Nominee'})")

        # Insert People
        for person_id, cat_name, is_winner in PERSON_NOMINEES:
            cat_id = get_or_create_category(conn, cat_name)
            conn.run("INSERT INTO nomination (eventid, categoryid, year, iswinner) VALUES (:e, :c, :y, :w)", 
                     e=EVENT_ID, c=cat_id, y=YEAR, w=is_winner)
            nom_id = conn.run("SELECT MAX(nominationid) FROM nomination")[0][0]
            conn.run("INSERT INTO person_nom (nomid, personid) VALUES (:n, :p)", n=nom_id, p=person_id)
            print(f"🎭 Added Person ID {person_id} -> {cat_name} ({'Winner' if is_winner else 'Nominee'})")

        conn.run("COMMIT")
        print("\n✅ Bulk upload complete! Check your website.")
    except Exception as e:
        conn.run("ROLLBACK")
        print("❌ Error during bulk upload:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
