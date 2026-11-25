"""Reset the UnderCover SQLite database from the seed files."""

from backend.db import DEFAULT_DB, seed, waiting_count


def reset() -> None:
    """Delete the database file and seed it again."""
    DEFAULT_DB.unlink(missing_ok=True)
    seed(DEFAULT_DB)
    print(f"Reset the queue: {waiting_count(DEFAULT_DB)} claims waiting.")


if __name__ == "__main__":
    reset()
