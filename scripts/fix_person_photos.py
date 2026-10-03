import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db
from services.importer import tmdb_get, POSTER_BASE

def fix_photos():
    conn = get_db()
    try:
        # Check people who use the placeholder or have null photos
        # People missing photos have photourl IS NULL or photourl='None'
        rows = conn.run("SELECT personid, name FROM person WHERE photourl IS NULL OR photourl = 'None' OR photourl = '';")
        print(f"Found {len(rows)} people missing photos.")

        updated = 0
        for pid, name in rows:
            # search tmdb for this person
            print(f"Searching TMDB for: {name}")
            try:
                res = tmdb_get("search/person", {"query": name})
                results = res.get("results", [])
                if results and results[0].get("profile_path"):
                    new_url = f"{POSTER_BASE}{results[0]['profile_path']}"
                    conn.run("UPDATE person SET photourl = :u WHERE personid = :id;", u=new_url, id=pid)
                    updated += 1
                    print(f"  -> Updated {name} with photo.")
                else:
                    print(f"  -> No photo found on TMDB for {name}.")
            except Exception as e:
                print(f"  -> Failed to fetch for {name}: {e}")
        
        print(f"Succesfully updated {updated} photos.")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_photos()
