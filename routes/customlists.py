from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import check_owner, get_current_user, get_optional_user, is_owner_or_admin
from database import get_db

router = APIRouter(prefix="/lists", tags=["Custom Lists"])

class ListCreate(BaseModel):
    userid: int
    listname: str
    description: str = ""
    ispublic: bool = False

class ListItem(BaseModel):
    userid: int
    listname: str
    mediaid: int

@router.get("/public")
def get_public_lists():
    # guests CAN view public lists
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT u.username, cl.userid, cl.listname, cl.description,
                      (SELECT COUNT(*) FROM customlistitem cli
                       WHERE cli.userid=cl.userid AND cli.listname=cl.listname) AS itemcount
               FROM customlist cl JOIN users u ON cl.userid=u.userid
               WHERE cl.ispublic=TRUE ORDER BY cl.listname;""")
        return [{"username": r[0], "userid": r[1], "listname": r[2],
                 "description": r[3], "itemcount": r[4]} for r in rows]
    finally:
        conn.close()

@router.get("/{user_id}")
def get_user_lists(user_id: int, current_user: dict | None = Depends(get_optional_user)):
    # the owner sees everything, everyone else only sees lists marked public
    only_public = not is_owner_or_admin(current_user, user_id)
    conn = get_db()
    try:
        rows = conn.run(
            """SELECT listname, description, ispublic FROM customlist
               WHERE userid=:id AND (ispublic OR NOT :only_public)
               ORDER BY listname;""",
            id=user_id, only_public=only_public)
        return [{"listname": r[0], "description": r[1], "ispublic": r[2]} for r in rows]
    finally:
        conn.close()

@router.get("/{user_id}/{listname}")
def get_list_items(user_id: int, listname: str, current_user: dict | None = Depends(get_optional_user)):
    conn = get_db()
    try:
        found = conn.run(
            "SELECT ispublic FROM customlist WHERE userid=:u AND listname=:l;",
            u=user_id, l=listname)
        if not found:
            # the owner just hasn't added anything yet (Favorites is created lazily)
            if is_owner_or_admin(current_user, user_id):
                return []
            raise HTTPException(status_code=404, detail="List not found")

        # private lists answer 404 to strangers, so they can't even tell it exists
        if not found[0][0] and not is_owner_or_admin(current_user, user_id):
            raise HTTPException(status_code=404, detail="List not found")

        rows = conn.run(
            """SELECT m.mediaid, m.title, m.avgrating, m.posterurl, m.mediatype, cli.addedat
               FROM customlistitem cli JOIN media m ON cli.mediaid=m.mediaid
               WHERE cli.userid=:u AND cli.listname=:l
               ORDER BY cli.addedat;""", u=user_id, l=listname)
        return [{"id": r[0], "title": r[1],
                 "avgrating": float(r[2]) if r[2] else None,
                 "posterurl": r[3], "type": r[4], "addedat": str(r[5])} for r in rows]
    finally:
        conn.close()

@router.post("/")
def create_list(data: ListCreate, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, data.userid)
    conn = get_db()
    try:
        existing = conn.run(
            "SELECT 1 FROM customlist WHERE userid=:u AND listname=:l;",
            u=data.userid, l=data.listname)
        if existing:
            return {"error": "List name already exists"}
        conn.run("BEGIN")
        conn.run(
            "INSERT INTO customlist (userid, listname, description, ispublic) VALUES (:u, :l, :d, :p);",
            u=data.userid, l=data.listname, d=data.description, p=data.ispublic)
        conn.run("COMMIT")
        return {"status": "created"}

    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to create list: " + str(e)}

    finally:
        conn.close()

@router.post("/add-item")
def add_item_to_list(item: ListItem, current_user: dict = Depends(get_current_user)):
    check_owner(current_user, item.userid)
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "INSERT INTO customlistitem (userid, listname, mediaid) VALUES (:u, :l, :m) ON CONFLICT DO NOTHING;",
            u=item.userid, l=item.listname, m=item.mediaid)
        conn.run("COMMIT")
        return {"status": "added"}

    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to add item to list: " + str(e)}

    finally:
        conn.close()

@router.patch("/visibility")
def toggle_visibility(userid: int, listname: str, ispublic: bool,
                      current_user: dict = Depends(get_current_user)):
    check_owner(current_user, userid)
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run(
            "UPDATE customlist SET ispublic=:p WHERE userid=:u AND listname=:l;",
            p=ispublic, u=userid, l=listname)
        conn.run("COMMIT")
        return {"status": "updated", "ispublic": ispublic}

    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to update list visibility: " + str(e)}
    finally:
        conn.close()

@router.delete("/{user_id}/{listname}/{media_id}")
def remove_item(user_id: int, listname: str, media_id: int,
                current_user: dict = Depends(get_current_user)):
    check_owner(current_user, user_id)
    conn = get_db()
    try:
        conn.run("BEGIN")
        conn.run("DELETE FROM customlistitem WHERE userid=:u AND listname=:l AND mediaid=:m;",
                 u=user_id, l=listname, m=media_id)
        conn.run("COMMIT")
        return {"status": "removed"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to remove item: " + str(e)}
    finally:
        conn.close()

@router.post("/{user_id}/{listname}/{media_id}")
def auto_add_item(user_id: int, listname: str, media_id: int,
                  current_user: dict = Depends(get_current_user)):
    """Used by the Favorite / Interested buttons. Creates the list on first use."""
    check_owner(current_user, user_id)
    conn = get_db()
    try:
        conn.run("BEGIN")
        existing_list = conn.run("SELECT 1 FROM customlist WHERE userid=:u AND listname=:l;", u=user_id, l=listname)
        if not existing_list:
            conn.run("INSERT INTO customlist (userid, listname, description) VALUES (:u, :l, 'Auto-generated list');", u=user_id, l=listname)

        conn.run("INSERT INTO customlistitem (userid, listname, mediaid) VALUES (:u, :l, :m) ON CONFLICT DO NOTHING;",
                 u=user_id, l=listname, m=media_id)
        conn.run("COMMIT")
        return {"status": "added"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to add favorite: " + str(e)}
    finally:
        conn.close()
