"""
Gives an existing account admin rights (sign up on the site first).

    python -m scripts.make_admin your_username
"""
import sys

from database import get_db


def main(username):
    conn = get_db()
    try:
        rows = conn.run("UPDATE users SET role = 'admin' WHERE LOWER(username) = LOWER(:u) RETURNING username;",
                        u=username)
    finally:
        conn.close()
    if rows:
        print(f"{rows[0][0]} is now an admin. Reload the site to see the Admin link.")
    else:
        print(f"No account called {username!r} - sign up on the site first.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.make_admin <username>")
    main(sys.argv[1])
