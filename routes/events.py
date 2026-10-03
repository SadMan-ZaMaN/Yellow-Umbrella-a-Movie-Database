from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import check_owner, check_owner_or_admin, get_current_user, get_optional_user, is_admin
from database import get_db

router = APIRouter(prefix="/events", tags=["Watch Events"])

class EventCreate(BaseModel):
    host_userid: int
    mediaid: int
    title: str
    description: str = ""
    platform: str = ""        # e.g. "Discord", "Teleparty"
    event_time: datetime
    stream_link: str = ""
    ispublic: bool = True

class RSVPCreate(BaseModel):
    eventid: int
    userid: int
    status: str               # "joined" or "interested"

@router.get("/")
def get_public_events():
    # guests CAN view events
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT we.eventid, u.username, m.title, we.title,
                      we.platform, we.event_time, we.description,
                      (SELECT COUNT(*) FROM event_rsvp er WHERE er.eventid=we.eventid) AS rsvp_count,
                      m.posterurl
               FROM watch_event we
               JOIN users u ON we.host_userid=u.userid
               JOIN media m ON we.mediaid=m.mediaid
               WHERE we.ispublic=TRUE
               ORDER BY we.event_time ASC;""") # ASC because upcoming first
        return [{"id": r[0], "host": r[1], "media": r[2], "title": r[3],
                 "platform": r[4], "time": str(r[5]), "description": r[6],
                 "rsvp_count": r[7], "poster": r[8]} for r in rows]
    finally:
        conn.close()

@router.get("/user/{user_id}")
def get_user_events(user_id: int, current_user: dict | None = Depends(get_optional_user)):
    """Fetch events hosted by OR RSVP'd by this user"""
    # which events someone has joined is their business, not everyone's
    check_owner_or_admin(current_user, user_id)
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT DISTINCT we.eventid, u.username, m.title, we.title,
                      we.platform, we.event_time, we.description,
                      (SELECT COUNT(*) FROM event_rsvp er WHERE er.eventid=we.eventid) AS rsvp_count,
                      m.posterurl,
                      CASE WHEN we.host_userid = :id THEN 'host' ELSE 'joiner' END as role
               FROM watch_event we
               JOIN users u ON we.host_userid=u.userid
               JOIN media m ON we.mediaid=m.mediaid
               LEFT JOIN event_rsvp er_check ON we.eventid = er_check.eventid
               WHERE we.host_userid = :id OR er_check.userid = :id
               ORDER BY we.event_time ASC;""", id=user_id)
        return [{"id": r[0], "host": r[1], "media": r[2], "title": r[3],
                 "platform": r[4], "time": str(r[5]), "description": r[6],
                 "rsvp_count": r[7], "poster": r[8], "user_role": r[9]} for r in rows]
    finally:
        conn.close()


@router.get("/{event_id}")
def get_event_detail(event_id: int, current_user: dict | None = Depends(get_optional_user)):
    # guests CAN view public event details
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT we.eventid, u.username, we.host_userid, m.title, m.posterurl,
                      we.title, we.description, we.platform, we.event_time,
                      we.ispublic
               FROM watch_event we
               JOIN users u ON we.host_userid=u.userid
               JOIN media m ON we.mediaid=m.mediaid
               WHERE we.eventid=:id;""", id=event_id)
        if not rows:
            return {"error": "Event not found"}
        r = rows[0]
        if not r[9] and not _is_host_or_guest(conn, event_id, r[2], current_user):
            return {"error": "Event not found"}
        event = {"id": r[0], "host": r[1], "host_userid": r[2],
                 "media_title": r[3], "poster": r[4], "title": r[5],
                 "description": r[6], "platform": r[7],
                 "time": str(r[8]), "ispublic": r[9]}

        rsvps = conn.run(
            """SELECT u.username, er.status FROM event_rsvp er
               JOIN users u ON er.userid=u.userid WHERE er.eventid=:id;""",
            id=event_id)
        event["rsvps"] = [{"username": r[0], "status": r[1]} for r in rsvps]
        return event
    finally:
        conn.close()


def _is_host_or_guest(conn, event_id: int, host_userid: int, current_user: dict | None) -> bool:
    if current_user is None:
        return False
    if current_user["userid"] == host_userid or is_admin(current_user):
        return True
    return bool(conn.run(
        "SELECT 1 FROM event_rsvp WHERE eventid=:e AND userid=:u;",
        e=event_id, u=current_user["userid"]))


@router.post("/")
def create_event(event: EventCreate, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, event.host_userid)
    conn = get_db()
    try:
        # Check for exact duplicate event
        existing = conn.run(
            "SELECT 1 FROM watch_event WHERE host_userid=:h AND mediaid=:m AND event_time=:et;",
            h=event.host_userid, m=event.mediaid, et=event.event_time)
        if existing:
            return {"error": "You already have a watch event for this media at the exact same time."}

        conn.run("BEGIN")
        conn.run(
            """INSERT INTO watch_event
               (host_userid, mediaid, title, description, platform, event_time, stream_link, ispublic)
               VALUES (:h, :m, :t, :d, :pl, :et, :sl, :ip);""",
            h=event.host_userid, m=event.mediaid, t=event.title,
            d=event.description, pl=event.platform,
            et=event.event_time, sl=event.stream_link, ip=event.ispublic)
        conn.run("COMMIT")
        return {"status": "event created"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to create event: " + str(e)}
    
    finally:
        conn.close()


@router.post("/rsvp")
def rsvp_event(rsvp: RSVPCreate, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, rsvp.userid)
    if rsvp.status not in ("joined", "interested"):
        return {"error": "status must be 'joined' or 'interested'"}
    conn = get_db()
    try:
        existing = conn.run(
            "SELECT status FROM event_rsvp WHERE eventid=:e AND userid=:u;",
            e=rsvp.eventid, u=rsvp.userid)
        
        conn.run("BEGIN")
        if existing:
            conn.run(
                "UPDATE event_rsvp SET status=:s WHERE eventid=:e AND userid=:u;",
                s=rsvp.status, e=rsvp.eventid, u=rsvp.userid)
            conn.run("COMMIT")
            return {"status": "updated"}
        
        conn.run(
            "INSERT INTO event_rsvp (eventid, userid, status) VALUES (:e, :u, :s);",
            e=rsvp.eventid, u=rsvp.userid, s=rsvp.status)
        conn.run("COMMIT")
        # If they joined, fetch the stream link to return
        if rsvp.status == "joined":
            link = conn.run(
                "SELECT stream_link FROM watch_event WHERE eventid=:e;", e=rsvp.eventid)
            return {"status": "joined", "stream_link": link[0][0] if link else None}
        return {"status": "marked as interested"}
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to RSVP: " + str(e)}
    
    finally:
        conn.close()


@router.get("/{event_id}/link/{user_id}")
def get_stream_link(event_id: int, user_id: int, current_user: dict = Depends(get_current_user)):
    """Only joined users can see the stream link"""
    # without this, passing someone else's id would hand over their link
    check_owner(current_user, user_id)
    conn = get_db()
    try:
        host = conn.run("SELECT stream_link FROM watch_event WHERE eventid=:e AND host_userid=:u;",
                        e=event_id, u=user_id)
        if host:
            return {"stream_link": host[0][0]}
        rsvp = conn.run(
            "SELECT status FROM event_rsvp WHERE eventid=:e AND userid=:u;",
            e=event_id, u=user_id)
        if not rsvp or rsvp[0][0] != "joined":
            return {"error": "You must join the event to get the link"}
        link = conn.run(
            "SELECT stream_link FROM watch_event WHERE eventid=:e;", e=event_id)
        return {"stream_link": link[0][0]}
    finally:
        conn.close()
