from fastapi import APIRouter

from database import get_db
from services.importer import fetch_and_save_person, tmdb_get

router = APIRouter(prefix="/people", tags=["People"])

@router.get("/search")
def search_people(q: str):
    conn = get_db()
    try:
        # 1 — search DB first
        rows = conn.run(
            "SELECT personid, name, photourl, birthdate FROM person WHERE name ILIKE :q;",
            q=f"%{q}%")

        if rows:
            return {"source": "database", "results": [
                {"id": r[0], "name": r[1], "photo": r[2],
                 "birthdate": str(r[3]) if r[3] else None}
                for r in rows]}

        # 2 — not in DB, search TMDB
        tmdb = tmdb_get("search/person", {"query": q})
        tmdb_results = tmdb.get("results", [])

        if not tmdb_results:
            return {"source": "not_found", "results": []}

        # 3 — save top 3 and return
        saved = []
        for item in tmdb_results[:3]:
            try:
                personid = fetch_and_save_person(conn, item["id"])
                saved.append({
                    "id": personid,
                    "name": item.get("name"),
                    "photo": f"https://image.tmdb.org/t/p/w500{item['profile_path']}"
                             if item.get("profile_path") else None,
                    "birthdate": None
                })
            except Exception as e:
                print(f"[auto-import error] {e}")

        return {"source": "tmdb_imported", "results": saved}

    finally:
        conn.close()

@router.get("/popular")
def get_popular_people():
    try:
        results = []
        for page in (1, 2):
            tmdb = tmdb_get("person/popular", {"page": page})
            results.extend(tmdb.get("results", []))
        
        valid_results = [p for p in results if p.get("profile_path")]
        
        popular = []
        for p in valid_results[:20]: # Return top 20 with photos
            known_for_list = [kf.get("title") or kf.get("name") for kf in p.get("known_for", [])]
            known_for_str = ", ".join(filter(None, known_for_list))
            
            popular.append({
                "id": p["id"],
                "name": p["name"],
                "photo": f"https://image.tmdb.org/t/p/w500{p['profile_path']}" if p.get("profile_path") else None,
                "known_for": known_for_str
            })
            
        return popular
    except Exception as e:
        return {"error": str(e)}

@router.get("/{person_id}")
def get_person_detail(person_id: int):
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT personid, name, bio, photourl, birthdate FROM person WHERE personid=:id;",
            id=person_id)
        if not rows:
            return {"error": "Not found"}
        r = rows[0]
        person = {"id": r[0], "name": r[1], "bio": r[2],
                  "photo": r[3], "birthdate": str(r[4]) if r[4] else None}

        actor = conn.run("SELECT agentname, unionstatus FROM actor WHERE actorid=:id;", id=person_id)
        if actor:
            person["role"] = "actor"
            filmography = conn.run(
                """SELECT m.mediaid, m.title, cm.rolename FROM cast_member cm
                   JOIN media m ON cm.mediaid=m.mediaid WHERE cm.actorid=:id;""",
                id=person_id)
            person["filmography"] = [{"id": f[0], "title": f[1], "role": f[2]} for f in filmography]

        director = conn.run("SELECT guildid FROM director WHERE directorid=:id;", id=person_id)
        if director:
            person["role"] = person.get("role", "") + " director"
            directed = conn.run(
                """SELECT m.mediaid, m.title FROM media_director md
                   JOIN media m ON md.mediaid=m.mediaid WHERE md.directorid=:id;""",
                id=person_id)
            person["directed"] = [{"id": d[0], "title": d[1]} for d in directed]

        return person
    finally:
        conn.close()
