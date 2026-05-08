import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from collector.storage import MessageStore, SpoolStore, open_sqlite
from collector.storage.migrations import migrate_database


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sample_item(message_id: str = "12345") -> dict:
    return {
        "feed_id": "tg_finance_news_daily",
        "source_id": "tg_finance_news_daily",
        "source_name": "Finance News Daily",
        "platform": "telegram",
        "message_id": message_id,
        "guid": f"tg_finance_news_daily:{message_id}",
        "url": f"https://t.me/FinanceNewsDaily/{message_id}",
        "title": "FED policy update",
        "summary": "The FED discussed rates and markets.",
        "raw_text_full": "FED policy update\nThe FED discussed rates and markets.",
        "pub_str": "2026-05-05T08:30:00+00:00",
        "external_url": "https://example.com/article",
        "external_urls": ["https://example.com/article", "https://example.com/report"],
        "preview_title": "Example Article",
        "collected_at": "2026-05-05T09:00:00+00:00",
    }


class SQLiteStorageTest(unittest.TestCase):
    def test_migrations_create_schema_and_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            messages_db = Path(temp_dir) / "messages.sqlite3"
            spool_db = Path(temp_dir) / "spool.sqlite3"

            applied_messages = migrate_database(
                messages_db,
                PROJECT_ROOT / "migrations/messages",
                require_fts5=True,
            )
            applied_spool = migrate_database(spool_db, PROJECT_ROOT / "migrations/spool")
            applied_messages_again = migrate_database(
                messages_db,
                PROJECT_ROOT / "migrations/messages",
                require_fts5=True,
            )

            self.assertEqual(applied_messages, ["0001_init"])
            self.assertEqual(applied_spool, ["0001_init"])
            self.assertEqual(applied_messages_again, [])

            with closing(open_sqlite(messages_db, readonly=True)) as conn:
                self.assertIsNotNone(
                    conn.execute(
                        "SELECT name FROM sqlite_master WHERE name = 'telegram_messages'"
                    ).fetchone()
                )
            with closing(open_sqlite(spool_db, readonly=True)) as conn:
                self.assertIsNotNone(
                    conn.execute(
                        "SELECT name FROM sqlite_master WHERE name = 'ingest_spool'"
                    ).fetchone()
                )

    def test_spool_store_appends_reads_and_acks_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spool_db = Path(temp_dir) / "spool.sqlite3"
            migrate_database(spool_db, PROJECT_ROOT / "migrations/spool")
            store = SpoolStore(spool_db)

            first_id = store.append_item(sample_item("100"))
            duplicate_id = store.append_item(sample_item("100"))
            pending = store.get_pending_batch()

            self.assertEqual(first_id, duplicate_id)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["guid"], "telegram:tg_finance_news_daily:100")
            self.assertEqual(pending[0]["payload"]["title"], "FED policy update")

            store.ack(first_id)

            self.assertEqual(store.get_pending_batch(), [])
            self.assertEqual(store.count_by_status(), {"acked": 1})

    def test_message_store_inserts_dedupes_and_indexes_fts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            messages_db = Path(temp_dir) / "messages.sqlite3"
            migrate_database(
                messages_db,
                PROJECT_ROOT / "migrations/messages",
                require_fts5=True,
            )
            store = MessageStore(messages_db)

            result = store.insert_messages([sample_item("200"), sample_item("200"), {}])
            message = store.get_by_guid("telegram:tg_finance_news_daily:200")
            search_results = store.search("FED", limit=10)

            self.assertEqual(result.inserted_count, 1)
            self.assertEqual(result.duplicate_count, 1)
            self.assertEqual(result.invalid_count, 1)
            self.assertEqual(result.fts_indexed_count, 1)
            self.assertEqual(result.fts_failed_count, 0)
            self.assertIsNotNone(message)
            self.assertEqual(message["external_url"], "https://example.com/article")
            self.assertIn("https://example.com/report", message["external_urls_json"])
            self.assertEqual(message["fts_indexed"], 1)
            self.assertEqual(len(search_results), 1)
            self.assertEqual(search_results[0]["guid"], "telegram:tg_finance_news_daily:200")

    def test_message_store_indexes_pending_fts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            messages_db = Path(temp_dir) / "messages.sqlite3"
            migrate_database(
                messages_db,
                PROJECT_ROOT / "migrations/messages",
                require_fts5=True,
            )
            store = MessageStore(messages_db)
            store.insert_messages([sample_item("300")])

            with closing(open_sqlite(messages_db)) as conn:
                with conn:
                    conn.execute(
                        "UPDATE telegram_messages SET fts_indexed = 0 WHERE message_id = '300'"
                    )

            indexed, failed = store.index_pending_fts(batch_size=1000)
            message = store.get_by_guid("telegram:tg_finance_news_daily:300")

            self.assertEqual((indexed, failed), (1, 0))
            self.assertEqual(message["fts_indexed"], 1)


if __name__ == "__main__":
    unittest.main()
