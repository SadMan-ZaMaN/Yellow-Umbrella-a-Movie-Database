from fastapi import APIRouter
from database import get_db

router = APIRouter(prefix="/awards", tags=["Awards"])

@router.get("/")
def get_all_award_events():
    """List all award shows (Oscars, Golden Globes etc.)"""
    conn = get_db()
    try:
        rows = conn.run("SELECT eventid, name, imageurl FROM award_event ORDER BY name;")
        return [{"id": r[0], "name": r[1], "imageurl": r[2]} for r in rows]
    finally:
        conn.close()

@router.get("/winners")
def get_all_winners():
    """Every winner across all award shows"""
    conn = get_db()
    try:
        # Media winners
        media_rows = conn.run("""
            SELECT ae.name, ac.name, n.year, m.title, 'media' as type
            FROM nomination n
            JOIN media_nom mn    ON n.nominationid = mn.nomid
            JOIN media m         ON mn.mediaid = m.mediaid
            JOIN award_event ae  ON n.eventid = ae.eventid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE n.iswinner = TRUE
            ORDER BY n.year DESC;
        """)

        # Person winners
        person_rows = conn.run("""
            SELECT ae.name, ac.name, n.year, p.name, 'person' as type
            FROM nomination n
            JOIN person_nom pn   ON n.nominationid = pn.nomid
            JOIN person p        ON pn.personid = p.personid
            JOIN award_event ae  ON n.eventid = ae.eventid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE n.iswinner = TRUE
            ORDER BY n.year DESC;
        """)

        winners = [{"event": r[0], "category": r[1], "year": r[2],
                    "name": r[3], "type": r[4]} for r in media_rows + person_rows]
        winners.sort(key=lambda x: x["year"], reverse=True)
        return winners
    finally:
        conn.close()

@router.get("/media/{media_id}")
def get_media_nominations(media_id: int):
    """All nominations for a specific movie/series/anime/game"""
    conn = get_db()
    try:
        rows = conn.run("""
            SELECT ae.name, ac.name, n.year, n.iswinner
            FROM nomination n
            JOIN media_nom mn      ON n.nominationid = mn.nomid
            JOIN award_event ae    ON n.eventid = ae.eventid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE mn.mediaid = :id
            ORDER BY n.year DESC;
        """, id=media_id)
        return [{"event": r[0], "category": r[1],
                 "year": r[2], "winner": r[3]} for r in rows]
    finally:
        conn.close()

@router.get("/person/{person_id}")
def get_person_nominations(person_id: int):
    """All nominations for a specific actor/director"""
    conn = get_db()
    try:
        rows = conn.run("""
            SELECT ae.name, ac.name, n.year, n.iswinner
            FROM nomination n
            JOIN person_nom pn     ON n.nominationid = pn.nomid
            JOIN award_event ae    ON n.eventid = ae.eventid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE pn.personid = :id
            ORDER BY n.year DESC;
        """, id=person_id)
        return [{"event": r[0], "category": r[1],
                 "year": r[2], "winner": r[3]} for r in rows]
    finally:
        conn.close()

@router.get("/event/{event_id}")
def get_event_nominations(event_id: int):
    """All nominations for one award show e.g. all Oscars"""
    conn = get_db()
    try:
        # Media nominations for this event
        media_rows = conn.run("""
            SELECT ac.name, n.year, m.title, n.iswinner, 'media' as type
            FROM nomination n
            JOIN media_nom mn      ON n.nominationid = mn.nomid
            JOIN media m           ON mn.mediaid = m.mediaid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE n.eventid = :id
            ORDER BY n.year DESC, ac.name;
        """, id=event_id)

        # Person nominations for this event
        person_rows = conn.run("""
            SELECT ac.name, n.year, p.name, n.iswinner, 'person' as type
            FROM nomination n
            JOIN person_nom pn     ON n.nominationid = pn.nomid
            JOIN person p          ON pn.personid = p.personid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE n.eventid = :id
            ORDER BY n.year DESC, ac.name;
        """, id=event_id)

        return [{"category": r[0], "year": r[1], "name": r[2],
                 "winner": r[3], "type": r[4]}
                for r in media_rows + person_rows]
    finally:
        conn.close()


@router.get("/comprehensive/{event_id}")
def get_comprehensive_event(event_id: int):
    """Hierarchical list for the TMDB replica award page"""
    conn = get_db()
    try:
        ev_rows = conn.run("SELECT name FROM award_event WHERE eventid=:id", id=event_id)
        if not ev_rows: return {"error": "Event not found"}
        event_name = ev_rows[0][0]
        
        # Get all person nominations
        p_noms = conn.run("""
            SELECT ac.name as category, n.year, p.name, p.photourl, n.iswinner, 
                   '' as subtitle
            FROM nomination n
            JOIN person_nom pn ON n.nominationid = pn.nomid
            JOIN person p ON pn.personid = p.personid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE n.eventid = :id
        """, id=event_id)
        
        # Get all media nominations
        m_noms = conn.run("""
            SELECT ac.name as category, n.year, m.title as name, m.posterurl as photourl, n.iswinner, 
                   m.releasedate as subtitle
            FROM nomination n
            JOIN media_nom mn ON n.nominationid = mn.nomid
            JOIN media m ON mn.mediaid = m.mediaid
            JOIN award_category ac ON n.categoryid = ac.categoryid
            WHERE n.eventid = :id
        """, id=event_id)
        
        years_map = {}
        for r in p_noms + m_noms:
            cat, year, name, photo, winner, sub = r
            if year not in years_map: years_map[year] = {}
            if cat not in years_map[year]: years_map[year][cat] = []
            
            # Format date to year if date
            if sub and len(str(sub).split('-')) == 3: sub = str(sub).split('-')[0]
                
            years_map[year][cat].append({
                "name": name,
                "photo": photo or "https://placehold.co/300x450/111111/ffffff?text=Photo",
                "subtitle": sub,
                "is_winner": winner
            })
            
        # Put winners first
        for y, cats in years_map.items():
            for c, noms in cats.items():
                noms.sort(key=lambda x: (not x["is_winner"], x["name"]))
                
        return {
            "event_name": event_name,
            "years": years_map
        }
    finally:
        conn.close()
