import os

import pg8000.native
from dotenv import load_dotenv

load_dotenv()


def get_db():
    return pg8000.native.Connection(
        database=os.getenv("DB_NAME", "imdb_project"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
    )
