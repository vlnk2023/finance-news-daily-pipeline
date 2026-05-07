"""SQLite-backed storage primitives."""

from .message_store import InsertMessagesResult, MessageStore
from .spool_store import SpoolStore
from .sqlite_connection import check_fts5_available, open_sqlite

__all__ = [
    "InsertMessagesResult",
    "MessageStore",
    "SpoolStore",
    "check_fts5_available",
    "open_sqlite",
]

