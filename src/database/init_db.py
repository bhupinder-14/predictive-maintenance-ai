"""Initialize the configured database schema using the default database URL."""

from src.config import DATABASE_URL

from .manager import Database


def main() -> None:
    database = Database(DATABASE_URL)
    database.initialize()
    database.dispose()
    print("Database schema initialized.")


if __name__ == "__main__":
    main()
