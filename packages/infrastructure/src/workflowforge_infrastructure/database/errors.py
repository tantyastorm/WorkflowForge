"""Database infrastructure errors."""


class DatabaseError(Exception):
    """Base error for database infrastructure failures."""


class DatabaseUnavailableError(DatabaseError):
    """Raised when the database dependency is unavailable."""
