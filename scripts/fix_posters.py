"""Fix broken poster URLs by searching TMDB with multiple strategies."""
import os, sys, time, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from database import get_db

TMDB_BASE = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
HEADERS = {"Authorization": f"Bearer {os.getenv('TMDB_TOKEN')}", "accept": "application/json"}

def search_poster(title, year=None):
    """Try multiple strategies to find a poster."""
    # Strategy 1: Search with year
    if year:
        try:
            r = requests.get(f"{TMDB_BASE}/search/movie", headers=HEADERS,
                             params={"query": title, "year": year}).json()
            if r.get("results"):
                for m in r["results"]:
                    if m.get("poster_path"):
                        return f"{POSTER_BASE}{m['poster_path']}", m["id"]
        except: pass
        time.sleep(0.3)
    
    # Strategy 2: Search without year
    try:
        r = requests.get(f"{TMDB_BASE}/search/movie", headers=HEADERS,
                         params={"query": title}).json()
        if r.get("results"):
            for m in r["results"]:
                if m.get("poster_path"):
                    return f"{POSTER_BASE}{m['poster_path']}", m["id"]
    except: pass
    time.sleep(0.3)
    
    # Strategy 3: Try TV search
    try:
        r = requests.get(f"{TMDB_BASE}/search/tv", headers=HEADERS,
                         params={"query": title}).json()
        if r.get("results"):
            for m in r["results"]:
                if m.get("poster_path"):
                    return f"{POSTER_BASE}{m['poster_path']}", m["id"]
    except: pass
    time.sleep(0.3)
    
    return None, None

conn = get_db()
try:
    # Get all media with bad or missing posters
    all_media = conn.run("""
        SELECT DISTINCT m.mediaid, m.title, m.posterurl, 
               EXTRACT(YEAR FROM m.releasedate)::int as yr
        FROM media m
        ORDER BY m.title
    """)
    
    fixed = 0
    checked = 0
    for mid, title, posterurl, yr in all_media:
        # Check if poster URL works
        if posterurl and posterurl.startswith("http"):
            try:
                resp = requests.head(posterurl, timeout=5)
                if resp.status_code == 200:
                    continue  # Poster is fine
            except:
                pass
        
        checked += 1
        poster, tmdb_id = search_poster(title, yr)
        if poster:
            conn.run("UPDATE media SET posterurl=:p WHERE mediaid=:id", p=poster, id=mid)
            fixed += 1
            print(f"  ✓ Fixed: {title} -> {poster[-40:]}")
        else:
            if not posterurl or posterurl == 'None':
                print(f"  ✗ No poster found: {title}")
    
    print(f"\nChecked {checked} media items, fixed {fixed} posters")
    print("Done!")
finally:
    conn.close()
