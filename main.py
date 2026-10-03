from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routes import (admin, anime, awards, comments, customlists, discover, events,
                    games, movies, people, reviews, series, stats, users, watchlist)

app = FastAPI(title="YellowUmbrella API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(movies.router)
app.include_router(series.router)
app.include_router(anime.router)
app.include_router(games.router)
app.include_router(people.router)
app.include_router(reviews.router)
app.include_router(watchlist.router)
app.include_router(customlists.router)
app.include_router(events.router)
app.include_router(users.router)
app.include_router(comments.router)
app.include_router(awards.router)
app.include_router(stats.router)
app.include_router(admin.router)
app.include_router(discover.router)

# The frontend is plain HTML/JS, served by the same app. This mount has to
# come last so it doesn't swallow the API routes above.
FRONTEND_DIR = Path(__file__).parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
