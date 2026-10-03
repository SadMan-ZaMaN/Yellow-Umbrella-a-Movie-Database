"""
Removes obscure titles that nobody has interacted with.

An older version of the search box imported TMDB's top three matches for
every half-typed query ("inter" -> "INTERSHELTER", "inter-pedestal", ...), so
the catalogue picked up a lot of things almost nobody has heard of. This
deletes titles that

  * have very few votes on TMDB / RAWG (or couldn't be matched there), and
  * have no reviews, comments, list entries, watch events or award
    nominations on our side.

Shows what it would delete unless you pass --apply.

    python -m scripts.prune_obscure            # dry run
    python -m scripts.prune_obscure --apply
"""
import sys

from database import get_db

MIN_VOTES = 50

CANDIDATES = """
    SELECT m.mediaid, m.title, m.mediatype, m.vote_count
    FROM media m
    WHERE COALESCE(m.vote_count, 0) < :min_votes
      AND NOT EXISTS (SELECT 1 FROM review r          WHERE r.mediaid = m.mediaid)
      AND NOT EXISTS (SELECT 1 FROM watchlist w       WHERE w.mediaid = m.mediaid)
      AND NOT EXISTS (SELECT 1 FROM customlistitem c  WHERE c.mediaid = m.mediaid)
      AND NOT EXISTS (SELECT 1 FROM media_comment mc  WHERE mc.mediaid = m.mediaid)
      AND NOT EXISTS (SELECT 1 FROM watch_event e     WHERE e.mediaid = m.mediaid)
      AND NOT EXISTS (SELECT 1 FROM media_nom n       WHERE n.mediaid = m.mediaid)
    ORDER BY m.mediatype, m.title;
"""


def main(apply=False):
    conn = get_db()
    try:
        rows = conn.run(CANDIDATES, min_votes=MIN_VOTES)
        for mediaid, title, mediatype, votes in rows:
            print(f"  {mediatype:7} #{mediaid:<5} {title}  ({votes or 0} votes)")
        print(f"\n{len(rows)} titles {'deleted' if apply else 'would be deleted (dry run, pass --apply)'}")
        if apply and rows:
            conn.run("BEGIN")
            # child rows (movie/series/game, cast, genres, trailers) cascade
            conn.run("DELETE FROM media WHERE mediaid = ANY(:ids);", ids=[r[0] for r in rows])
            conn.run("COMMIT")
    finally:
        conn.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
