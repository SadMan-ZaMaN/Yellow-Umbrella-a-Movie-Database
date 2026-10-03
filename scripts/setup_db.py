"""
Creates the database (if it doesn't exist) and loads the schema, using the
settings in .env - no psql needed.

    python -m scripts.setup_db              # empty database, ready to fill
    python -m scripts.setup_db --sample     # plus a small offline sample dataset

Run it again on an existing database and it applies sql/upgrade.sql instead,
so it's also how you update a database made with an older version.
"""
import os
import sys
from pathlib import Path

import pg8000.native
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_NAME = os.getenv("DB_NAME", "imdb_project")
SETTINGS = {
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
}


def run_file(conn, name):
    print(f"  running sql/{name}")
    conn.run((ROOT / "sql" / name).read_text(encoding="utf-8"))


def main(sample=False):
    if not (ROOT / ".env").exists():
        sys.exit("No .env file yet - copy .env.example to .env and fill it in first.")

    try:
        server = pg8000.native.Connection(database="postgres", **SETTINGS)
    except Exception as e:
        sys.exit(f"Couldn't connect to PostgreSQL: {e}\n"
                 f"Check that PostgreSQL is running and DB_USER / DB_PASSWORD in .env are right.")
    try:
        if not server.run("SELECT 1 FROM pg_database WHERE datname = :n;", n=DB_NAME):
            # CREATE DATABASE can't take a parameter; the name comes from our own .env
            server.run(f'CREATE DATABASE "{DB_NAME}";')
            print(f"Created database {DB_NAME}")
    finally:
        server.close()

    conn = pg8000.native.Connection(database=DB_NAME, **SETTINGS)
    try:
        fresh = not conn.run("SELECT 1 FROM information_schema.tables WHERE table_name = 'media';")
        if sample and not fresh:
            sys.exit(f"Not loading the sample data: it wipes every table, and {DB_NAME} already has data.")

        if fresh:
            print("Loading the schema...")
            run_file(conn, "schema.sql")
        else:
            print(f"{DB_NAME} already has tables - bringing it up to date...")
            run_file(conn, "upgrade.sql")
        run_file(conn, "functions.sql")
        if sample:
            run_file(conn, "seed.sql")
    finally:
        conn.close()

    print("\nDone.")
    for key in ("TMDB_TOKEN", "RAWG_KEY", "JWT_SECRET_KEY"):
        if not os.getenv(key):
            print(f"Note: {key} is empty in .env - see the README for where to get it.")


if __name__ == "__main__":
    main(sample="--sample" in sys.argv)
